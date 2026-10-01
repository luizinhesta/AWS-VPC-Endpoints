# -*- coding: utf-8 -*-
"""
Verificacao local leve (somente local - NAO acessa a AWS).

Objetivo: confirmar que `config.py`, os modulos de servico e `app.py` importam e
compilam, e fazer um smoke test da rota `GET /health` sem depender de credenciais
AWS nem de servicos AWS reais.

Como funciona sem AWS:
- As chamadas boto3 de inicializacao (clientes/recursos) sao criadas de forma
  "preguicosa" o suficiente para o import nao exigir credenciais.
- A rota /health nao realiza nenhuma chamada AWS, portanto responde 200 mesmo
  sem acesso a nuvem.

Uso:
    python sanity_check.py

Observacao: esta verificacao NAO cria nem altera recursos AWS. E apenas um teste
local de importacao/compilacao e um smoke test do health check.
"""

import os
import sys

# Garante que o diretorio do app esteja no path para importar config/servicos.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Evita qualquer tentativa de uso de credenciais/arquivos AWS durante o import.
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")


def check_imports():
    """Importa config, servicos e app para validar compilacao."""
    import config  # noqa: F401
    from services import (  # noqa: F401
        dynamodb_service,
        logging_service,
        s3_service,
        secrets_service,
    )
    import app  # noqa: F401

    print("[OK] Imports e compilacao de config, servicos e app bem-sucedidos.")
    return app


def check_health(app_module):
    """Smoke test local da rota GET /health (sem AWS)."""
    client = app_module.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200, "Esperado HTTP 200 em /health, obtido %s" % resp.status_code
    print("[OK] GET /health respondeu 200 localmente.")


def main():
    try:
        app_module = check_imports()
    except Exception as exc:  # noqa: BLE001
        print("[FALHA] Erro ao importar os modulos: %s" % exc)
        return 1

    try:
        check_health(app_module)
    except Exception as exc:  # noqa: BLE001
        print("[FALHA] Smoke test da rota /health falhou: %s" % exc)
        return 1

    print("Verificacao local concluida com sucesso. Nenhum recurso AWS foi acessado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
