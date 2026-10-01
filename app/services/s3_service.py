# -*- coding: utf-8 -*-
"""
Servico de armazenamento da foto do perfil no bucket S3 privado.

Acessado pela EC2 por meio do Gateway Endpoint do S3 (rota/prefix list na route
table). A entrega da foto ao navegador e feita por PROXY da aplicacao (ver rota
`GET /photo`), de modo que todo acesso ao S3 ocorra a partir da EC2 passando
pelo Gateway Endpoint.

O bucket permanece privado (Block Public Access habilitado); nenhum objeto e
tornado publico. Todas as chaves ficam sob o prefixo `profiles/`.
"""

import logging

import boto3
from botocore.exceptions import ClientError

from config import AWS_REGION, BUCKET_NAME

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3", region_name=AWS_REGION)

# Prefixo obrigatorio para todas as chaves de objeto do laboratorio.
_PHOTO_PREFIX = "profiles/"


def upload_photo(file_bytes, content_type, photo_key):
    """Envia os bytes da foto para o S3 e retorna a `photo_key` usada.

    Nao define ACL publica - o bucket e privado. A chave deve estar sob o
    prefixo `profiles/`.
    """
    if not photo_key.startswith(_PHOTO_PREFIX):
        raise ValueError("A chave da foto deve ficar sob o prefixo 'profiles/'.")
    _s3.put_object(
        Bucket=BUCKET_NAME,
        Key=photo_key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return photo_key


def get_photo_bytes(photo_key):
    """Obtem os bytes da foto via s3:GetObject (abordagem de proxy).

    Retorna uma tupla (bytes, content_type). O content_type cai para
    `application/octet-stream` quando o objeto nao expoe o metadado.
    """
    obj = _s3.get_object(Bucket=BUCKET_NAME, Key=photo_key)
    body = obj["Body"].read()
    content_type = obj.get("ContentType", "application/octet-stream")
    return body, content_type


def photo_exists(photo_key):
    """Verifica a existencia do objeto no S3 via head_object.

    Retorna False quando o objeto nao existe (404/NoSuchKey) e relanca outras
    falhas inesperadas.
    """
    try:
        _s3.head_object(Bucket=BUCKET_NAME, Key=photo_key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise
