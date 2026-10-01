# -*- coding: utf-8 -*-
"""
Servico de leitura de configuracao no AWS Secrets Manager.

Acessado pela EC2 por meio do Interface Endpoint do Secrets Manager.
Usa a cadeia de credenciais padrao do boto3 (IAM Role da instancia) - sem
chaves embutidas.
"""

import json
import logging

import boto3

from config import AWS_REGION, SECRET_NAME

logger = logging.getLogger(__name__)

# Valor padrao (fallback) exibido quando a leitura do segredo falha, para que a
# pagina continue renderizavel mesmo com o Secrets Manager indisponivel.
_DEFAULT_CONFIG = {"APP_NAME": "AWS Profile Lab", "APP_ENV": "lab"}

# Cliente boto3 e cache em memoria da configuracao lida.
_sm = boto3.client("secretsmanager", region_name=AWS_REGION)
_cache = None


def get_app_config():
    """Le o segredo {APP_NAME, APP_ENV} e aplica cache em memoria.

    Retorna sempre um dict utilizavel: em caso de falha de leitura, devolve um
    valor padrao de APP_NAME sem lancar excecao (a pagina deve continuar
    renderizavel). A sinalizacao de erro para o CloudWatch e responsabilidade
    da camada web (que emite o evento ERROR).
    """
    global _cache
    if _cache is not None:
        return _cache

    try:
        resp = _sm.get_secret_value(SecretId=SECRET_NAME)
        _cache = json.loads(resp["SecretString"])
        # Garante APP_NAME presente mesmo que o segredo esteja incompleto.
        if "APP_NAME" not in _cache:
            _cache["APP_NAME"] = _DEFAULT_CONFIG["APP_NAME"]
        return _cache
    except Exception as exc:  # noqa: BLE001 - fallback intencional
        logger.warning("Falha ao ler o segredo da aplicacao: %s", exc)
        # Nao cacheia o fallback para permitir nova tentativa posterior.
        return dict(_DEFAULT_CONFIG)
