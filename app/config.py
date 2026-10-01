# -*- coding: utf-8 -*-
"""
Constantes de configuracao do laboratorio AWS VPC Endpoints.

Observacoes importantes:
- Nenhuma credencial AWS e definida aqui. O boto3 resolve as credenciais pela
  cadeia padrao (IAM Role da instancia EC2 via Instance Profile).
- O valor de BUCKET_NAME e um placeholder e DEVE ser ajustado pelo usuario para o
  nome unico do bucket S3 criado manualmente no Console AWS.
"""

# Regiao AWS do laboratorio.
AWS_REGION = "us-east-1"

# Nome do bucket S3 privado onde a foto do perfil e armazenada.
# PLACEHOLDER: substitua pelo nome unico do bucket criado no Console AWS.
BUCKET_NAME = "aws-vpc-endpoints-lab-REPLACE-ME"

# Nome da tabela DynamoDB que guarda os dados do perfil.
TABLE_NAME = "profiles"

# Nome do segredo no Secrets Manager contendo o JSON {APP_NAME, APP_ENV}.
SECRET_NAME = "aws-vpc-endpoints-lab/app-config"

# Log group e log stream no CloudWatch Logs para os eventos de dominio.
LOG_GROUP = "/aws-vpc-endpoints-lab/app"
LOG_STREAM = "app-events"

# Identificador fixo do unico perfil suportado pelo laboratorio.
PROFILE_ID = "profile-001"

# Chave (key) do objeto da foto no S3, sempre sob o prefixo "profiles/".
PHOTO_KEY = "profiles/profile-001/avatar.jpg"

# Porta em que a aplicacao Flask escuta na EC2.
APP_PORT = 5000
