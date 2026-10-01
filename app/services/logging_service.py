# -*- coding: utf-8 -*-
"""
Servico de emissao de eventos de dominio no CloudWatch Logs.

Acessado pela EC2 por meio do Interface Endpoint do CloudWatch Logs (porta 443).
Usa a cadeia de credenciais padrao do boto3 (IAM Role) - sem chaves embutidas.

Eventos suportados:
  APPLICATION_STARTED, PROFILE_CREATED, PROFILE_UPDATED,
  PHOTO_UPLOADED, PHOTO_CHANGED, ERROR.

Tolerancia a falhas: se o envio ao CloudWatch Logs falhar, a acao principal da
aplicacao NAO deve ser bloqueada; a falha e apenas registrada localmente.
"""

import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

from config import AWS_REGION, LOG_GROUP, LOG_STREAM

logger = logging.getLogger(__name__)

_logs = boto3.client("logs", region_name=AWS_REGION)

# Conjunto de eventos de dominio validos (documental; nao bloqueia o envio).
VALID_EVENTS = {
    "APPLICATION_STARTED",
    "PROFILE_CREATED",
    "PROFILE_UPDATED",
    "PHOTO_UPLOADED",
    "PHOTO_CHANGED",
    "ERROR",
}


def init_logging():
    """Garante a existencia do log group e do log stream.

    Idempotente: ignora os erros de "ja existe" (ResourceAlreadyExistsException).
    Falhas de rede/permissao sao toleradas e registradas localmente, para nao
    bloquear o startup da aplicacao.
    """
    try:
        _logs.create_log_group(logGroupName=LOG_GROUP)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "ResourceAlreadyExistsException":
            logger.warning("Falha ao criar log group '%s': %s", LOG_GROUP, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha inesperada ao criar log group '%s': %s", LOG_GROUP, exc)

    try:
        _logs.create_log_stream(logGroupName=LOG_GROUP, logStreamName=LOG_STREAM)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "ResourceAlreadyExistsException":
            logger.warning("Falha ao criar log stream '%s': %s", LOG_STREAM, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha inesperada ao criar log stream '%s': %s", LOG_STREAM, exc)


def emit(event_type, detail):
    """Envia um evento JSON ao CloudWatch Logs via logs:PutLogEvents.

    Nunca propaga excecoes: qualquer falha de envio e tolerada e registrada
    localmente, de modo que a acao principal da aplicacao conclua normalmente.
    """
    message = json.dumps({"event": event_type, "detail": detail}, ensure_ascii=False)
    try:
        _logs.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=LOG_STREAM,
            logEvents=[{"timestamp": int(time.time() * 1000), "message": message}],
        )
    except Exception as exc:  # noqa: BLE001 - tolerancia intencional a falhas de log
        logger.warning("Falha ao emitir evento '%s' no CloudWatch Logs: %s", event_type, exc)
