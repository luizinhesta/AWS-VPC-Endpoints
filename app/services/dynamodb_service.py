# -*- coding: utf-8 -*-
"""
Servico de persistencia do perfil na tabela DynamoDB `profiles`.

Acessado pela EC2 por meio do Gateway Endpoint do DynamoDB (rota/prefix list na
route table). Usa a cadeia de credenciais padrao do boto3 (IAM Role) - sem
chaves embutidas.

Regras de dados:
- Chave primaria (partition key): `profileId`.
- `updatedAt` e sempre gravado em formato ISO-8601 no momento do salvamento.
- Apenas a referencia `photoKey` (string) e persistida; nunca bytes de imagem.
"""

from datetime import datetime, timezone

import boto3

from config import AWS_REGION, TABLE_NAME

_table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)


def _now_iso8601():
    """Retorna o instante atual em UTC no formato ISO-8601 (ex.: 2025-01-15T13:45:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_profile(profile_id):
    """Le o item do perfil. Retorna o dict do item ou None quando nao existir."""
    resp = _table.get_item(Key={"profileId": profile_id})
    return resp.get("Item")


def put_profile(profile):
    """Cria (ou substitui) o item do perfil.

    Grava `updatedAt` em ISO-8601 se ainda nao estiver presente. Garante que
    nenhum conteudo binario de imagem seja persistido - somente a referencia
    textual `photoKey`.
    """
    item = dict(profile)
    item.setdefault("updatedAt", _now_iso8601())
    _validate_no_binary_photo(item)
    _table.put_item(Item=item)


def update_profile(profile_id, changes):
    """Atualiza os atributos do perfil existente.

    Reescreve `updatedAt` em ISO-8601 e persiste apenas a referencia `photoKey`.
    Nao altera o atributo `profileId` (chave primaria).
    """
    attrs = dict(changes)
    attrs.pop("profileId", None)
    attrs["updatedAt"] = _now_iso8601()
    _validate_no_binary_photo(attrs)

    expr_names = {}
    expr_values = {}
    set_parts = []
    for idx, (key, value) in enumerate(attrs.items()):
        name_placeholder = "#f%d" % idx
        value_placeholder = ":v%d" % idx
        expr_names[name_placeholder] = key
        expr_values[value_placeholder] = value
        set_parts.append("%s = %s" % (name_placeholder, value_placeholder))

    _table.update_item(
        Key={"profileId": profile_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def _validate_no_binary_photo(item):
    """Garante que `photoKey`, quando presente, seja apenas uma referencia textual."""
    photo_key = item.get("photoKey")
    if photo_key is not None and not isinstance(photo_key, str):
        raise ValueError("photoKey deve ser uma referencia textual (string), nunca bytes de imagem.")
