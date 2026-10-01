# AWS VPC Endpoints Lab — Aplicação de Perfil (Flask)

Laboratório prático na AWS (região `us-east-1`) para **visualizar na prática a diferença entre Gateway VPC Endpoints e Interface VPC Endpoints**. A aplicação é um mini cartão de perfil de usuário escrito em **Flask (Python)**, hospedado em uma única instância **EC2 sem IP público**, em subnet privada, exposta à internet apenas por um **Application Load Balancer (ALB) público**.

> Toda a infraestrutura AWS é criada **manualmente pelo usuário no Console AWS**. Nenhum recurso é provisionado por automação (sem Terraform, CloudFormation, CDK ou AWS CLI). O passo a passo completo está em [`IMPLANTACAO.md`](./IMPLANTACAO.md).

---

## 1. Objetivo didático

O laboratório mostra, na prática, como dois tipos de VPC Endpoint funcionam de maneiras diferentes:

- **Gateway VPC Endpoints** (usados por **S3** e **DynamoDB**): funcionam adicionando uma rota para uma *prefix list* gerenciada pela AWS na *route table* da subnet. **Não têm ENI, não têm IP próprio e não usam Security Group.** São gratuitos e controlados por rota e por *Endpoint Policy*.
- **Interface VPC Endpoints** (usados por **Secrets Manager**, **CloudWatch Logs** e **Systems Manager / Session Manager**): funcionam criando uma **ENI** (interface de rede) com IP privado dentro da subnet, via **AWS PrivateLink**. **Têm Security Group** e exigem liberação explícita da porta **443**. Têm custo por hora e por GB processado.

O exercício final (Etapa 19 do `IMPLANTACAO.md`) remove a rota `0.0.0.0/0 -> NAT Gateway` da route table privada e comprova que a aplicação **continua funcionando** (S3, DynamoDB, Secrets Manager, CloudWatch Logs e Session Manager seguem acessíveis pelos endpoints), enquanto o acesso geral à internet (ex.: `sudo dnf update`) **para de funcionar**.

---

## 2. Arquitetura resumida

```
Internet
   |
   v
Internet Gateway (IGW)
   |
   v
ALB público  (subnet pública, HTTP 80)
   |  tráfego da app na porta 5000 (SG-ALB -> SG-EC2)
   v
EC2 Flask  (subnet privada, SEM IP público)
   |
   +-- S3 .................. via GATEWAY Endpoint (rota/prefix list, sem SG)   -> foto de perfil
   +-- DynamoDB ............ via GATEWAY Endpoint (rota/prefix list, sem SG)   -> dados do perfil
   +-- Secrets Manager ..... via INTERFACE Endpoint (ENI + SG + 443)           -> APP_NAME / APP_ENV
   +-- CloudWatch Logs ..... via INTERFACE Endpoint (ENI + SG + 443)           -> eventos de domínio
   +-- Systems Manager ..... via INTERFACE Endpoints (ssm/ssmmessages/ec2messages) -> Session Manager (admin)
```

Pontos-chave:

- **Internet -> Internet Gateway -> ALB público -> EC2 privada**: o ALB é o único ponto de entrada da internet; a EC2 nunca é diretamente acessível.
- **S3 e DynamoDB via Gateway Endpoints**: acesso roteado por *prefix list* na route table privada.
- **Secrets Manager, CloudWatch Logs e SSM via Interface Endpoints**: acesso por ENI/PrivateLink na porta 443, protegido pelo `SG-INTERFACE-ENDPOINTS`.
- **Acesso administrativo apenas via Session Manager**: sem SSH na porta 22, sem bastion, sem par de chaves.
- **Arquitetura sem alta disponibilidade**: AZ única, uma única EC2.

A separação de armazenamento é deliberada: os dados do perfil ficam no **DynamoDB** (tabela `profiles`, chave primária `profileId`) e a foto fica no **S3** (bucket privado). O DynamoDB guarda apenas a referência `photoKey`, **nunca** a imagem binária. A foto é entregue ao navegador **por proxy da aplicação** (rota `GET /photo`), garantindo que todo acesso ao S3 passe pelo Gateway Endpoint.

---

## 3. Estrutura de pastas do projeto

```
aws-endpoints/
├── README.md                   # Este arquivo (visão geral)
├── IMPLANTACAO.md              # Passo a passo manual no Console AWS (Etapas 1 a 19 + endurecimento)
└── app/
    ├── config.py               # Constantes do laboratório (bucket, tabela, segredo, região, log group)
    ├── app.py                  # Rotas Flask e orquestração dos serviços
    ├── requirements.txt        # Dependências: Flask, boto3
    ├── sanity_check.py         # Verificação local leve (import/compile e smoke de /health, sem AWS real)
    ├── services/
    │   ├── __init__.py
    │   ├── s3_service.py        # Upload/download da foto no S3 (Gateway Endpoint)
    │   ├── dynamodb_service.py  # CRUD do perfil no DynamoDB (Gateway Endpoint)
    │   ├── secrets_service.py   # Leitura do segredo no Secrets Manager (Interface Endpoint)
    │   └── logging_service.py   # Emissão de eventos no CloudWatch Logs (Interface Endpoint)
    ├── templates/
    │   ├── index.html           # Página inicial: cartão de perfil OU formulário de criação
    │   └── edit.html            # Formulário de edição
    └── static/
        ├── css/style.css        # Estilo do cartão e dos formulários
        └── js/app.js            # Preview da foto antes do envio
```

---

## 4. Rotas da aplicação

| Método | Rota      | Descrição |
|--------|-----------|-----------|
| `GET`  | `/`       | Página inicial. Exibe o **cartão de perfil** quando `profile-001` existe, ou o **formulário de criação** quando ainda não existe. Mostra o `APP_NAME` lido do Secrets Manager. |
| `GET`  | `/edit`   | Formulário de edição preenchido com os dados atuais do perfil. |
| `POST` | `/save`   | Cria ou atualiza o perfil (nome, e-mail, profissão, cidade, bio, interesses), trata o upload de foto e redireciona (HTTP 302) para `/`. |
| `GET`  | `/photo`  | Entrega a foto do perfil **por proxy** via `s3:GetObject` (Gateway Endpoint). Responde HTTP 404 quando não há `photoKey`. |
| `GET`  | `/health` | Health check do Target Group do ALB. Responde HTTP 200. |

---

## 5. Como configurar

A configuração fica em [`app/config.py`](./app/config.py). Ajuste os valores conforme os recursos criados no Console AWS:

- **`BUCKET_NAME`** — **principal placeholder a ajustar.** O valor padrão é `aws-vpc-endpoints-lab-REPLACE-ME`; substitua pelo nome único do bucket S3 que você criar (nomes de bucket são globais e precisam ser únicos).
- **`SECRET_NAME`** — `aws-vpc-endpoints-lab/app-config` (confirme que o segredo foi criado com esse nome).
- **`TABLE_NAME`** — `profiles` (confirme o nome da tabela DynamoDB).
- **`LOG_GROUP`** — `/aws-vpc-endpoints-lab/app`.
- **`LOG_STREAM`** — `app-events`.
- **`AWS_REGION`** — `us-east-1`.

Os valores `PROFILE_ID` (`profile-001`), `PHOTO_KEY` (`profiles/profile-001/avatar.jpg`) e `APP_PORT` (`5000`) normalmente não precisam ser alterados.

> **Nenhuma credencial AWS é definida no `config.py`.** O `boto3` resolve as credenciais pela cadeia padrão, usando a **IAM Role** associada à instância EC2 via Instance Profile.

---

## 6. Como rodar na EC2 (resumo)

Os comandos detalhados, incluindo como copiar o projeto e manter o serviço no ar, estão na **Etapa 15** do [`IMPLANTACAO.md`](./IMPLANTACAO.md). Em resumo, dentro da EC2 (acesso via Session Manager):

1. Instalar Python 3 e pip (Amazon Linux 2023 já traz Python 3).
2. Ajustar o `BUCKET_NAME` em `app/config.py`.
3. Instalar as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Iniciar a aplicação na porta `5000`:
   ```bash
   python3 app.py
   ```

A aplicação escuta em `0.0.0.0:5000` para que o ALB a alcance na subnet privada.

### Teste local sem AWS

Para uma verificação local leve (import/compilação e smoke test da rota `GET /health`) **sem acessar serviços AWS reais e sem exigir credenciais**, use:

```bash
python3 app/sanity_check.py
```

---

## 7. Observação de segurança

- Credenciais exclusivamente via **IAM Role** (Instance Profile da EC2). **Sem chaves de acesso hardcoded** no código.
- **Sem arquivo `.env` com credenciais** e sem credenciais AWS salvas na instância.
- Bucket S3 **privado** (Block Public Access habilitado); a foto é servida apenas pela aplicação.
- EC2 **sem IP público**, **sem SSH 22** exposto; acesso administrativo somente por **Session Manager**.
- IAM Role de **menor privilégio**: acesso restrito ao bucket do lab, à tabela `profiles` e ao segredo específico.

---

## 8. Próximo passo

Siga o guia completo de implantação manual no Console AWS, com as Etapas 1 a 19 e as seções de endurecimento, em **[`IMPLANTACAO.md`](./IMPLANTACAO.md)**.
