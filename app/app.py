# -*- coding: utf-8 -*-
"""
Camada web Flask do laboratorio AWS VPC Endpoints.

Orquestra os modulos de servico (Secrets Manager, DynamoDB, S3 e CloudWatch
Logs), todos acessados por boto3 com a cadeia de credenciais padrao (IAM Role
da instancia EC2) - sem chaves embutidas.

Rotas:
  GET  /        -> cartao de perfil (perfil existe) OU formulario de criacao
  GET  /health  -> health check do Target Group do ALB (HTTP 200)
  GET  /edit    -> formulario de edicao preenchido
  POST /save    -> cria/atualiza o perfil e redireciona (302) para /
  GET  /photo   -> entrega a foto por proxy via s3:GetObject (404 quando ausente)
"""

import logging

from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)

from config import APP_PORT, PHOTO_KEY, PROFILE_ID
from services import dynamodb_service, logging_service, s3_service, secrets_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Content-Types aceitos para a foto do perfil.
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Startup: inicializa logging e emite APPLICATION_STARTED.
# ---------------------------------------------------------------------------
def _startup():
    """Garante o log group/stream e emite o evento de inicializacao.

    Tolerante a falhas: nenhum erro de logging deve impedir a aplicacao de subir.
    """
    try:
        logging_service.init_logging()
        logging_service.emit("APPLICATION_STARTED", {"profileId": PROFILE_ID})
    except Exception as exc:  # noqa: BLE001 - startup nunca deve falhar por log
        logger.warning("Falha no startup de logging: %s", exc)


_startup()


def _app_name():
    """Le o APP_NAME do Secrets Manager; usa fallback e emite ERROR em falha."""
    try:
        return secrets_service.get_app_config().get("APP_NAME", "AWS Profile Lab")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao obter APP_NAME: %s", exc)
        logging_service.emit("ERROR", {"where": "get_app_config", "message": str(exc)})
        return "AWS Profile Lab"


def _normalize_interests(raw):
    """Converte uma string de interesses separada por virgulas em lista limpa."""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# GET /health -> 200 para o Target Group do ALB.
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    return "OK", 200


# ---------------------------------------------------------------------------
# GET / -> cartao de perfil OU formulario de criacao.
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    app_name = _app_name()
    try:
        profile = dynamodb_service.get_profile(PROFILE_ID)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao ler o perfil no DynamoDB")
        logging_service.emit("ERROR", {"where": "get_profile", "message": str(exc)})
        return (
            render_template(
                "index.html",
                mode="error",
                app_name=app_name,
                error_message="Nao foi possivel carregar o perfil. "
                "Verifique o Gateway Endpoint do DynamoDB e tente novamente.",
            ),
            502,
        )

    if profile is None:
        return render_template("index.html", mode="create", app_name=app_name)

    has_photo = bool(profile.get("photoKey"))
    return render_template(
        "index.html",
        mode="card",
        app_name=app_name,
        profile=profile,
        has_photo=has_photo,
    )


# ---------------------------------------------------------------------------
# GET /edit -> formulario de edicao preenchido.
# ---------------------------------------------------------------------------
@app.route("/edit")
def edit():
    app_name = _app_name()
    try:
        profile = dynamodb_service.get_profile(PROFILE_ID) or {}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao ler o perfil para edicao")
        logging_service.emit("ERROR", {"where": "get_profile/edit", "message": str(exc)})
        profile = {}

    interests = profile.get("interests") or []
    interests_text = ", ".join(interests) if isinstance(interests, list) else str(interests)
    return render_template(
        "edit.html",
        app_name=app_name,
        profile=profile,
        interests_text=interests_text,
    )


# ---------------------------------------------------------------------------
# POST /save -> cria/atualiza o perfil, trata upload de foto e redireciona.
# ---------------------------------------------------------------------------
@app.route("/save", methods=["POST"])
def save():
    app_name = _app_name()

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()

    # Validacao: name e email obrigatorios.
    if not name or not email:
        try:
            profile = dynamodb_service.get_profile(PROFILE_ID) or {}
        except Exception:  # noqa: BLE001
            profile = {}
        interests = profile.get("interests") or []
        interests_text = ", ".join(interests) if isinstance(interests, list) else str(interests)
        return (
            render_template(
                "edit.html",
                app_name=app_name,
                profile=request.form,
                interests_text=request.form.get("interests", interests_text),
                error_message="Os campos Nome e E-mail sao obrigatorios.",
            ),
            400,
        )

    # Le o estado atual para decidir entre criar ou atualizar.
    try:
        existing = dynamodb_service.get_profile(PROFILE_ID)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao ler o perfil no salvamento")
        logging_service.emit("ERROR", {"where": "get_profile/save", "message": str(exc)})
        return _dependency_error()

    is_new = existing is None

    # Define a photoKey inicial: nova (None) ou preserva a anterior.
    photo_key = None if is_new else existing.get("photoKey")

    # Trata upload de foto, se enviada.
    uploaded = request.files.get("photo")
    if uploaded and uploaded.filename:
        content_type = (uploaded.content_type or "").lower()
        if content_type not in _ALLOWED_IMAGE_TYPES:
            interests = (existing or {}).get("interests") or []
            interests_text = ", ".join(interests) if isinstance(interests, list) else str(interests)
            return (
                render_template(
                    "edit.html",
                    app_name=app_name,
                    profile=request.form,
                    interests_text=request.form.get("interests", interests_text),
                    error_message="Formato de imagem invalido. Envie um arquivo image/jpeg ou image/png.",
                ),
                400,
            )
        try:
            file_bytes = uploaded.read()
            s3_service.upload_photo(file_bytes, content_type, PHOTO_KEY)
            photo_key = PHOTO_KEY
            logging_service.emit(
                "PHOTO_UPLOADED" if is_new else "PHOTO_CHANGED",
                {"key": photo_key},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao enviar a foto para o S3")
            logging_service.emit("ERROR", {"where": "upload_photo", "message": str(exc)})
            return _dependency_error()

    # Monta o item do perfil (sem bytes de imagem - apenas photoKey).
    profile = {
        "profileId": PROFILE_ID,
        "name": name,
        "email": email,
        "profession": (request.form.get("profession") or "").strip(),
        "city": (request.form.get("city") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
        "interests": _normalize_interests(request.form.get("interests")),
    }
    if photo_key:
        profile["photoKey"] = photo_key

    # Persiste criando ou atualizando.
    try:
        if is_new:
            dynamodb_service.put_profile(profile)
            logging_service.emit("PROFILE_CREATED", {"profileId": PROFILE_ID})
        else:
            dynamodb_service.update_profile(PROFILE_ID, profile)
            logging_service.emit("PROFILE_UPDATED", {"profileId": PROFILE_ID})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao persistir o perfil no DynamoDB")
        logging_service.emit("ERROR", {"where": "save_profile", "message": str(exc)})
        return _dependency_error()

    return redirect(url_for("home"), code=302)


# ---------------------------------------------------------------------------
# GET /photo -> entrega a foto por proxy via s3:GetObject.
# ---------------------------------------------------------------------------
@app.route("/photo")
def photo():
    try:
        profile = dynamodb_service.get_profile(PROFILE_ID)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao ler o perfil para servir a foto")
        logging_service.emit("ERROR", {"where": "get_profile/photo", "message": str(exc)})
        abort(502)

    if profile is None or not profile.get("photoKey"):
        abort(404)

    try:
        body, content_type = s3_service.get_photo_bytes(profile["photoKey"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao obter a foto do S3")
        logging_service.emit("ERROR", {"where": "get_photo_bytes", "message": str(exc)})
        abort(404)

    resp = Response(body, mimetype=content_type)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _dependency_error():
    """Resposta padronizada quando uma dependencia AWS esta indisponivel."""
    app_name = _app_name()
    return (
        render_template(
            "index.html",
            mode="error",
            app_name=app_name,
            error_message="Uma dependencia AWS esta indisponivel no momento. "
            "Verifique os VPC Endpoints e a IAM Role e tente novamente.",
        ),
        502,
    )


if __name__ == "__main__":
    # host 0.0.0.0 para que o ALB alcance a aplicacao na subnet privada.
    app.run(host="0.0.0.0", port=APP_PORT)
