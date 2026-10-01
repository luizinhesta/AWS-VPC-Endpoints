# Guia de Implantação Manual no Console AWS — `IMPLANTACAO.md`

Passo a passo **manual** para montar toda a infraestrutura do laboratório **AWS VPC Endpoints** no **Console AWS**, na região **`us-east-1`**, em **AZ única** e **sem alta disponibilidade** (uma única EC2).

> **Importante:** nenhum recurso é criado por automação. Todos os passos abaixo são executados manualmente no Console AWS. A aplicação em execução é o próprio teste do laboratório.

## Convenções e valores de referência

Os nomes e valores abaixo vêm de `app/config.py` e devem ser usados exatamente como estão (exceto `BUCKET_NAME`, que é um placeholder único a definir por você):

| Item | Valor |
|------|-------|
| Região | `us-east-1` |
| VPC CIDR (sugerido) | `10.0.0.0/16` |
| Subnet pública (sugerida) | `10.0.1.0/24` |
| Subnet privada (sugerida) | `10.0.2.0/24` |
| Tabela DynamoDB (`TABLE_NAME`) | `profiles` |
| Chave primária da tabela | `profileId` (String) |
| Segredo (`SECRET_NAME`) | `aws-vpc-endpoints-lab/app-config` |
| Conteúdo do segredo | `{"APP_NAME":"AWS Profile Lab","APP_ENV":"lab"}` |
| Log group (`LOG_GROUP`) | `/aws-vpc-endpoints-lab/app` |
| Log stream (`LOG_STREAM`) | `app-events` |
| Perfil (`PROFILE_ID`) | `profile-001` |
| Chave da foto (`PHOTO_KEY`) | `profiles/profile-001/avatar.jpg` |
| Porta da aplicação (`APP_PORT`) | `5000` |
| Bucket S3 (`BUCKET_NAME`) | **placeholder único a definir** (ex.: `aws-vpc-endpoints-lab-SEU-SUFIXO`) |

Nomes de recursos de rede/segurança usados neste guia (defina as tags `Name` iguais para facilitar): `VPC-LAB`, `SUBNET-PUB`, `SUBNET-PRIV`, `IGW-LAB`, `RT-PUB`, `RT-PRIV`, `NAT-LAB`, `SG-ALB`, `SG-EC2`, `SG-INTERFACE-ENDPOINTS`, `ROLE-EC2-LAB`.

---

## Etapa 1 — VPC

**O que criar:** uma VPC chamada `VPC-LAB` com CIDR `10.0.0.0/16`.

**Por que criar:** é a rede isolada onde todos os demais recursos (subnets, EC2, endpoints) vão residir. Define o espaço de endereçamento privado do laboratório.

**Dependências:** nenhuma. É o primeiro recurso.

**O que selecionar no Console:**
- VPC > *Your VPCs* > **Create VPC**.
- Selecione **VPC only** (vamos criar subnets, IGW e rotas manualmente para fins didáticos).
- *IPv4 CIDR*: `10.0.0.0/16`.
- *Tenancy*: Default.
- Tag `Name` = `VPC-LAB`.

**Como validar:** a VPC aparece na lista com estado **Available** e CIDR `10.0.0.0/16`.

---

## Etapa 2 — Subnets (1 pública, 1 privada, mesma AZ)

**O que criar:** duas subnets na **mesma Availability Zone** (ex.: `us-east-1a`):
- `SUBNET-PUB` — `10.0.1.0/24` (pública).
- `SUBNET-PRIV` — `10.0.2.0/24` (privada).

**Por que criar:** separar o ponto de entrada da internet (ALB e NAT na subnet pública) do servidor de aplicação (EC2 e Interface Endpoints na subnet privada). A mesma AZ mantém o laboratório simples (sem alta disponibilidade).

**Dependências:** Etapa 1 (VPC).

**O que selecionar no Console:**
- VPC > *Subnets* > **Create subnet** > selecione `VPC-LAB`.
- Subnet 1: Name `SUBNET-PUB`, AZ `us-east-1a`, CIDR `10.0.1.0/24`.
- Subnet 2: Name `SUBNET-PRIV`, **mesma AZ** `us-east-1a`, CIDR `10.0.2.0/24`.
- (A associação a route tables e o auto-assign de IP público são configurados nas etapas seguintes.)

**Como validar:** as duas subnets aparecem **Available**, ambas na mesma AZ, dentro de `VPC-LAB`.

---

## Etapa 3 — Internet Gateway

**O que criar:** um Internet Gateway `IGW-LAB` anexado à `VPC-LAB`.

**Por que criar:** fornece a saída/entrada da internet para a subnet pública (necessário para o ALB público e para a rota de saída do NAT Gateway).

**Dependências:** Etapa 1 (VPC).

**O que selecionar no Console:**
- VPC > *Internet gateways* > **Create internet gateway** > Name `IGW-LAB` > **Create**.
- Selecione o IGW > **Actions** > **Attach to VPC** > selecione `VPC-LAB`.

**Como validar:** o IGW aparece com estado **Attached** à `VPC-LAB`.

---

## Etapa 4 — Route Tables

**O que criar:** duas route tables na `VPC-LAB`:
- `RT-PUB` (pública): rota `0.0.0.0/0 -> IGW-LAB`, associada à `SUBNET-PUB`.
- `RT-PRIV` (privada): rota `0.0.0.0/0 -> NAT-LAB` (o NAT é criado na Etapa 5), associada à `SUBNET-PRIV`.

**Por que criar:** o roteamento é o que define o comportamento de rede. A subnet pública alcança a internet diretamente pelo IGW; a subnet privada só alcança a internet por meio do NAT (saída, nunca entrada). A `RT-PRIV` será o palco do exercício final (Etapa 19).

**Dependências:** Etapa 1 (VPC), Etapa 2 (subnets), Etapa 3 (IGW). A rota do NAT em `RT-PRIV` só pode ser concluída depois da Etapa 5.

**O que selecionar no Console:**
- VPC > *Route tables* > **Create route table** (duas vezes), ambas em `VPC-LAB`, com Names `RT-PUB` e `RT-PRIV`.
- Em `RT-PUB` > **Routes** > **Edit routes** > adicionar `Destination 0.0.0.0/0` com *Target* = `IGW-LAB`.
- Em `RT-PUB` > **Subnet associations** > associar `SUBNET-PUB`.
- Em `RT-PRIV` > **Subnet associations** > associar `SUBNET-PRIV`.
- Em `RT-PRIV` > **Routes** > **Edit routes** > adicionar `Destination 0.0.0.0/0` com *Target* = `NAT Gateway NAT-LAB` (após a Etapa 5).

**Como validar:** `SUBNET-PUB` está associada à `RT-PUB` (com rota para o IGW) e `SUBNET-PRIV` à `RT-PRIV`. Após a Etapa 5, `RT-PRIV` mostra a rota `0.0.0.0/0 -> nat-...`.

---

## Etapa 5 — NAT Gateway + Elastic IP

**O que criar:** um NAT Gateway `NAT-LAB` na **subnet pública** (`SUBNET-PUB`), com um Elastic IP alocado.

**Por que criar:** permite que a EC2 na subnet privada faça **saída** para a internet (instalar pacotes com `dnf`/`pip` e registrar o SSM Agent) **antes** de os endpoints estarem completos. No exercício final (Etapa 19), a rota para o NAT é removida para comprovar que os endpoints bastam.

**Dependências:** Etapa 2 (subnet pública), Etapa 3 (IGW anexado).

**O que selecionar no Console:**
- VPC > *NAT gateways* > **Create NAT gateway**.
- Name `NAT-LAB`; *Subnet* = `SUBNET-PUB`; *Connectivity type* = **Public**.
- **Allocate Elastic IP** para associar um EIP.
- Depois de criado, volte à Etapa 4 e conclua a rota `0.0.0.0/0 -> NAT-LAB` em `RT-PRIV`.

**Como validar:** o NAT Gateway fica **Available** com um Elastic IP associado; a `RT-PRIV` passa a conter a rota `0.0.0.0/0 -> nat-...`.

---

## Etapa 6 — Security Groups

**O que criar:** três Security Groups na `VPC-LAB`.

| Security Group | Entrada (Inbound) | Saída (Outbound) |
|----------------|-------------------|------------------|
| **SG-ALB** | HTTP `80` de `0.0.0.0/0` | TCP `5000` para `SG-EC2` |
| **SG-EC2** | TCP `5000` apenas de `SG-ALB`; **sem SSH 22** | TCP `443` (para `SG-INTERFACE-ENDPOINTS` e, na fase inicial, para a internet via NAT) |
| **SG-INTERFACE-ENDPOINTS** | TCP `443` apenas de `SG-EC2` | — (padrão) |

**Por que criar:** os Security Groups implementam o modelo de rede de menor exposição. O ALB é o único ponto público; a EC2 só aceita tráfego da app vindo do ALB; os Interface Endpoints só aceitam 443 vindo da EC2. **Este é o ponto didático central:** os Interface Endpoints usam Security Group (`SG-INTERFACE-ENDPOINTS` na porta 443), enquanto os **Gateway Endpoints (S3 e DynamoDB) NÃO usam Security Group** — eles são controlados por rota (prefix list) e por Endpoint Policy.

> **Nota sobre HTTPS 443/ACM (documentado, não aplicado):** para habilitar HTTPS no ALB seria necessário um certificado no **AWS Certificate Manager (ACM)**, um listener `443` no ALB e a liberação de `443` de `0.0.0.0/0` no `SG-ALB`. Como o laboratório foca em VPC Endpoints e não em TLS, mantemos apenas HTTP `80`.

**Dependências:** Etapa 1 (VPC). Como há referências cruzadas entre SGs, crie os três primeiro (sem regras) e depois edite as regras referenciando-os.

**O que selecionar no Console:**
- VPC/EC2 > *Security Groups* > **Create security group** (três vezes, em `VPC-LAB`): `SG-ALB`, `SG-EC2`, `SG-INTERFACE-ENDPOINTS`.
- **SG-ALB** — Inbound: *Type* HTTP, *Port* 80, *Source* `0.0.0.0/0`. Outbound: *Type* Custom TCP, *Port* 5000, *Destination* = `SG-EC2`.
- **SG-EC2** — Inbound: *Type* Custom TCP, *Port* 5000, *Source* = `SG-ALB`. **Não** adicionar regra SSH 22. Outbound: *Type* HTTPS, *Port* 443, *Destination* = `SG-INTERFACE-ENDPOINTS` (e manter saída 443 geral enquanto o NAT existir).
- **SG-INTERFACE-ENDPOINTS** — Inbound: *Type* HTTPS, *Port* 443, *Source* = `SG-EC2`.

**Como validar:** cada SG mostra exatamente as regras acima. Confirme que `SG-EC2` **não** possui regra de entrada na porta 22.

---

## Etapa 7 — IAM Role + Instance Profile (menor privilégio)

**O que criar:** uma IAM Role `ROLE-EC2-LAB` para o serviço EC2, com Instance Profile, concedendo o **menor privilégio** necessário:

- **S3**: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` — somente no bucket do lab.
- **DynamoDB**: `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem` — somente na tabela `profiles`.
- **Secrets Manager**: `secretsmanager:GetSecretValue` — somente no segredo da aplicação.
- **CloudWatch Logs**: `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` — no log group do lab.
- **Systems Manager**: política gerenciada `AmazonSSMManagedInstanceCore` — para o Session Manager.

**Por que criar:** a aplicação não usa chaves de acesso; o `boto3` resolve credenciais pela IAM Role da instância. O menor privilégio garante que a instância só acesse exatamente os recursos do laboratório (propriedade de segurança do design).

**Dependências:** idealmente após conhecer os ARNs do bucket (Etapa 8), tabela (Etapa 9) e segredo (Etapa 10). Você pode criar a Role agora com placeholders e refinar os ARNs depois, ou criar as Etapas 8-10 primeiro e então anexar as policies com os ARNs reais.

**O que selecionar no Console:**
- IAM > *Roles* > **Create role** > *Trusted entity* = **AWS service** > *Use case* = **EC2**.
- Anexe a política gerenciada **`AmazonSSMManagedInstanceCore`**.
- Crie e anexe uma **política inline** (ou gerenciada pelo cliente) com os JSONs de exemplo abaixo (substitua os placeholders `<...>`).
- Nome da Role: `ROLE-EC2-LAB`. O Console cria o Instance Profile automaticamente.

**Exemplo de policy — S3 (restrita ao bucket):**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "S3BucketDoLab",
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": ["arn:aws:s3:::<bucket-do-lab>/*"]
  }]
}
```

**Exemplo de policy — DynamoDB (restrita à tabela `profiles`):**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "DynamoDBTabelaProfiles",
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
    "Resource": ["arn:aws:dynamodb:us-east-1:<account-id>:table/profiles"]
  }]
}
```

**Exemplo de policy — Secrets Manager (restrita ao segredo):**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "SegredoDaAplicacao",
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": ["arn:aws:secretsmanager:us-east-1:<account-id>:secret:aws-vpc-endpoints-lab/app-config-*"]
  }]
}
```

**Exemplo de policy — CloudWatch Logs (restrita ao log group):**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "LogGroupDoLab",
    "Effect": "Allow",
    "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
    "Resource": [
      "arn:aws:logs:us-east-1:<account-id>:log-group:/aws-vpc-endpoints-lab/app",
      "arn:aws:logs:us-east-1:<account-id>:log-group:/aws-vpc-endpoints-lab/app:*"
    ]
  }]
}
```

**Como validar:** a Role `ROLE-EC2-LAB` existe, possui as policies acima e a `AmazonSSMManagedInstanceCore`, e tem um Instance Profile associado (visível na criação da EC2 na Etapa 14).

---

## Etapa 8 — S3 bucket privado

**O que criar:** um bucket S3 **privado** com nome único (ex.: `aws-vpc-endpoints-lab-SEU-SUFIXO`), **Block Public Access habilitado** e **sem** hospedagem de site estático.

**Por que criar:** armazena a foto do perfil (objeto `profiles/profile-001/avatar.jpg`). O bucket é privado porque a foto é servida apenas pela aplicação (proxy via `GET /photo`), garantindo que o acesso ao S3 passe pelo Gateway Endpoint.

**Dependências:** nenhuma técnica, mas o nome do bucket deve ser definido antes da instalação da app (Etapa 15), pois precisa ser ajustado em `config.py`.

**O que selecionar no Console:**
- S3 > **Create bucket** > *Region* `us-east-1`.
- *Bucket name*: seu nome único.
- Mantenha **Block all public access** marcado (ON).
- **Não** habilite *Static website hosting*.

**Como validar:** o bucket aparece com *Access: Bucket and objects not public*. **Lembre-se de ajustar `BUCKET_NAME` em `app/config.py`** com este nome (atualmente o placeholder é `aws-vpc-endpoints-lab-REPLACE-ME`).

---

## Etapa 9 — DynamoDB tabela `profiles`

**O que criar:** uma tabela DynamoDB chamada `profiles` com chave primária (partition key) `profileId` do tipo **String**.

**Por que criar:** armazena os dados do perfil (nome, e-mail, profissão, cidade, bio, interesses, `photoKey`, `updatedAt`). O design separa dados (DynamoDB) de imagem (S3).

**Dependências:** nenhuma.

**O que selecionar no Console:**
- DynamoDB > *Tables* > **Create table**.
- *Table name*: `profiles`.
- *Partition key*: `profileId`, tipo **String**.
- Capacidade: **On-demand** (padrão simples) é suficiente para o laboratório.

**Como validar:** a tabela `profiles` fica **Active**, com partition key `profileId (String)`.

---

## Etapa 10 — Secrets Manager (segredo da aplicação)

**O que criar:** um segredo chamado `aws-vpc-endpoints-lab/app-config` com o conteúdo:
```json
{"APP_NAME":"AWS Profile Lab","APP_ENV":"lab"}
```

**Por que criar:** a aplicação lê o `APP_NAME` deste segredo via Interface Endpoint do Secrets Manager e o exibe na página, demonstrando o uso de um Interface Endpoint.

**Dependências:** nenhuma.

**O que selecionar no Console:**
- Secrets Manager > **Store a new secret** > *Other type of secret*.
- Em *Key/value* ou *Plaintext*, insira o JSON acima.
- *Secret name*: `aws-vpc-endpoints-lab/app-config`.
- Rotação: desabilitada (não necessária no laboratório).

**Como validar:** o segredo aparece com o nome exato e, ao *Retrieve secret value*, mostra `APP_NAME` e `APP_ENV`.

---

## Etapa 11 — Gateway Endpoint do S3

**O que criar:** um VPC Endpoint do tipo **Gateway** para o serviço `com.amazonaws.us-east-1.s3`, associado à **route table privada** (`RT-PRIV`).

**Por que criar:** permite que a EC2 na subnet privada acesse o S3 **sem** passar pela internet/NAT. É um dos protagonistas do laboratório (tipo Gateway).

**Dependências:** Etapa 1 (VPC), Etapa 4 (`RT-PRIV`).

**O que selecionar no Console:**
- VPC > *Endpoints* > **Create endpoint**.
- *Service category*: AWS services. Procure por **s3** e selecione o de **Type: Gateway** (`com.amazonaws.us-east-1.s3`).
- *VPC*: `VPC-LAB`.
- *Route tables*: marque `RT-PRIV`.
- *Policy*: **Full access** nesta fase (restrição fica para a seção de Endurecimento).

**Como validar:** o endpoint fica **Available** e a `RT-PRIV` passa a mostrar uma rota para a **prefix list** do S3 (`pl-...`) apontando para o endpoint (`vpce-...`). **Observe que não há Security Group associado** — Gateway Endpoints são controlados por rota.

---

## Etapa 12 — Gateway Endpoint do DynamoDB

**O que criar:** um VPC Endpoint do tipo **Gateway** para o serviço `com.amazonaws.us-east-1.dynamodb`, associado à **route table privada** (`RT-PRIV`).

**Por que criar:** permite que a EC2 acesse a tabela `profiles` sem internet/NAT. Segundo Gateway Endpoint do laboratório.

**Dependências:** Etapa 1 (VPC), Etapa 4 (`RT-PRIV`).

**O que selecionar no Console:**
- VPC > *Endpoints* > **Create endpoint**.
- Procure por **dynamodb** e selecione o de **Type: Gateway** (`com.amazonaws.us-east-1.dynamodb`).
- *VPC*: `VPC-LAB`.
- *Route tables*: marque `RT-PRIV`.
- *Policy*: **Full access** nesta fase.

**Como validar:** o endpoint fica **Available** e a `RT-PRIV` mostra a rota da **prefix list** do DynamoDB apontando para o `vpce-...`. Novamente, **sem Security Group**.

---

## Etapa 13 — Interface Endpoints (Secrets Manager, Logs e SSM)

**O que criar:** os seguintes Interface Endpoints (AWS PrivateLink), todos com **DNS privado habilitado**, na **subnet privada** (`SUBNET-PRIV`) e com o Security Group **`SG-INTERFACE-ENDPOINTS`**:

- `com.amazonaws.us-east-1.secretsmanager`
- `com.amazonaws.us-east-1.logs`
- `com.amazonaws.us-east-1.ssm`
- `com.amazonaws.us-east-1.ssmmessages`
- `com.amazonaws.us-east-1.ec2messages`

**Por que criar:** permitem que a aplicação acesse Secrets Manager e CloudWatch Logs, e que o **Session Manager** funcione (`ssm`, `ssmmessages`, `ec2messages`) em uma EC2 **sem** acesso à internet. Diferente dos Gateway Endpoints, **cada Interface Endpoint cria uma ENI com IP privado na subnet, usa Security Group e se comunica via PrivateLink na porta 443**.

**Dependências:** Etapa 2 (`SUBNET-PRIV`), Etapa 6 (`SG-INTERFACE-ENDPOINTS`).

**O que selecionar no Console (repita para cada serviço):**
- VPC > *Endpoints* > **Create endpoint**.
- *Service category*: AWS services. Procure pelo nome do serviço e selecione o de **Type: Interface**.
- *VPC*: `VPC-LAB`.
- *Subnets*: selecione `SUBNET-PRIV` (AZ única).
- **Enable DNS name** (DNS privado) marcado.
- *Security groups*: `SG-INTERFACE-ENDPOINTS`.
- *Policy*: Full access nesta fase.

**Como validar:** cada Interface Endpoint fica **Available**, mostra uma **ENI** com IP privado na `SUBNET-PRIV`, tem o `SG-INTERFACE-ENDPOINTS` associado e *Private DNS* habilitado. A partir da EC2 (após a Etapa 14), `nslookup secretsmanager.us-east-1.amazonaws.com` deve resolver para um IP privado `10.0.2.x`.

---

## Etapa 14 — EC2 (Amazon Linux 2023, sem IP público)

**O que criar:** uma instância EC2 (ex.: `t3.micro`) com **Amazon Linux 2023**, **sem IP público**, na **subnet privada** (`SUBNET-PRIV`), com o **Instance Profile** da Etapa 7 (`ROLE-EC2-LAB`) e o Security Group `SG-EC2`. **Sem par de chaves / sem SSH**; o acesso será apenas por **Session Manager**.

**Por que criar:** é o servidor que roda a aplicação Flask. Fica em subnet privada e sem IP público para não ser acessível diretamente da internet; o acesso administrativo é feito por Session Manager pelos Interface Endpoints do SSM.

**Dependências:** Etapa 2 (`SUBNET-PRIV`), Etapa 6 (`SG-EC2`), Etapa 7 (Instance Profile), Etapa 13 (endpoints do SSM para o Session Manager funcionar sem internet). O NAT (Etapa 5) ainda deve estar ativo nesta fase para instalar pacotes.

**O que selecionar no Console:**
- EC2 > **Launch instance**.
- *AMI*: **Amazon Linux 2023**.
- *Instance type*: `t3.micro` (ou `t3.small`).
- *Key pair*: **Proceed without a key pair** (sem SSH).
- *Network*: `VPC-LAB`, *Subnet* `SUBNET-PRIV`, **Auto-assign public IP = Disable**.
- *Security group*: `SG-EC2`.
- *Advanced details* > *IAM instance profile*: `ROLE-EC2-LAB`.

**Como validar:** a instância fica **Running** sem IP público. Em EC2 > *Connect* > **Session Manager**, o botão **Connect** fica habilitado e abre um shell (confirma que o SSM Agent se registrou pelos endpoints/NAT). Se o Session Manager não conectar, verifique a Role (`AmazonSSMManagedInstanceCore`) e os endpoints `ssm`/`ssmmessages`/`ec2messages`.

---

## Etapa 15 — Instalação da aplicação na EC2

**O que criar/fazer:** instalar e iniciar a aplicação Flask **dentro da EC2**, acessando por **Session Manager**.

**Por que criar:** colocar a aplicação em execução na porta `5000`, pronta para ser registrada no Target Group do ALB (Etapa 16).

**Dependências:** Etapa 14 (EC2 acessível por Session Manager), NAT ativo (Etapa 5) para instalar pacotes, e `BUCKET_NAME` já definido (Etapa 8).

**O que selecionar/executar no Console e na EC2:**
- EC2 > *Connect* > **Session Manager** > **Connect**.
- Comandos dentro da EC2 (os comentários explicam cada passo):

```bash
# Vira o usuario ec2-user e vai para o home
sudo su - ec2-user

# Instala Python 3, pip e git (Amazon Linux 2023 ja traz Python 3)
sudo dnf install -y python3 python3-pip git

# Copie/clone o projeto. Opcao A (git), se o repositorio estiver acessivel:
git clone <URL-do-repositorio> aws-endpoints
# Opcao B (S3): se voce subiu o projeto para um bucket seu, baixe com:
# aws s3 cp s3://<seu-bucket>/aws-endpoints/ ./aws-endpoints/ --recursive

cd aws-endpoints/app

# Ajuste o BUCKET_NAME no config.py para o nome real do bucket (Etapa 8).
# Edite com nano/vi, por exemplo:
# nano config.py   -> trocar aws-vpc-endpoints-lab-REPLACE-ME pelo seu bucket

# Instala as dependencias (Flask e boto3)
pip install -r requirements.txt

# Inicia a aplicacao na porta 5000 (teste rapido em primeiro plano)
python3 app.py
```

Para manter a aplicação rodando após fechar a sessão, use `nohup` ou um serviço `systemd`:

```bash
# Opcao simples com nohup (fica em background):
nohup python3 app.py > /home/ec2-user/app.log 2>&1 &

# Opcao recomendada: servico systemd. Crie /etc/systemd/system/profile-app.service:
sudo tee /etc/systemd/system/profile-app.service > /dev/null <<'EOF'
[Unit]
Description=AWS VPC Endpoints Lab - Profile App (Flask)
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/aws-endpoints/app
ExecStart=/usr/bin/python3 /home/ec2-user/aws-endpoints/app/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now profile-app
sudo systemctl status profile-app
```

**Como validar:** dentro da EC2, `curl http://localhost:5000/health` retorna `OK` (HTTP 200). Com `systemd`, `sudo systemctl status profile-app` mostra **active (running)**.

---

## Etapa 16 — ALB público

**O que criar:** um Application Load Balancer **público** na subnet pública, com um **Target Group** HTTP na porta `5000`, *health check path* `/health`, com a EC2 registrada, e um **listener HTTP 80** encaminhando para o Target Group.

**Por que criar:** é o ponto de entrada público da aplicação. Encaminha o tráfego HTTP 80 da internet para a porta `5000` da EC2 privada.

**Dependências:** Etapa 2 (subnet pública), Etapa 6 (`SG-ALB`), Etapa 15 (app rodando na porta 5000). Observação: um ALB normalmente exige **duas subnets em AZs distintas**; para o laboratório em AZ única, se necessário crie uma segunda subnet pública mínima apenas para satisfazer o ALB, mantendo a EC2 na única AZ privada.

**O que selecionar no Console:**
- EC2 > *Load Balancers* > **Create load balancer** > **Application Load Balancer**.
- *Scheme*: **Internet-facing**.
- *VPC*: `VPC-LAB`; *Mappings*: subnet(s) pública(s).
- *Security group*: `SG-ALB`.
- *Listener* HTTP `80` > **Create target group**:
  - *Target type*: Instances; *Protocol/Port*: HTTP `5000`.
  - *Health check path*: `/health`.
  - Registre a instância EC2 no Target Group.

**Como validar:** o Target Group mostra o alvo como **healthy**. Abrir `http://<DNS-do-ALB>/` no navegador exibe o formulário de criação de perfil (ou o cartão, se já criado).

---

## Etapa 17 — CloudWatch Logs

**O que criar/verificar:** o log group `/aws-vpc-endpoints-lab/app` com o log stream `app-events`, criados automaticamente pela aplicação na inicialização.

**Por que criar:** a aplicação emite eventos de domínio (`APPLICATION_STARTED`, `PROFILE_CREATED`, `PROFILE_UPDATED`, `PHOTO_UPLOADED`, `PHOTO_CHANGED`, `ERROR`) via Interface Endpoint do CloudWatch Logs, permitindo observar o comportamento pelos logs.

**Dependências:** Etapa 7 (permissões de Logs na Role), Etapa 13 (Interface Endpoint `logs`), Etapa 15 (app em execução).

**O que selecionar no Console:**
- CloudWatch > *Logs* > *Log groups* > procure por `/aws-vpc-endpoints-lab/app`.
- Abra o log stream `app-events`.

**Como validar:** o log group existe e o stream `app-events` contém pelo menos o evento `APPLICATION_STARTED` (gerado no startup) e, após usar a aplicação, eventos como `PROFILE_CREATED`.

---

## Etapa 18 — Teste funcional

**O que fazer:** validar a aplicação de ponta a ponta pelo DNS do ALB.

**Por que fazer:** confirmar que todas as integrações (DynamoDB, S3, Secrets Manager, CloudWatch Logs) e o acesso administrativo (Session Manager) funcionam antes do exercício final.

**Dependências:** Etapas 8 a 17 concluídas.

**O que selecionar/executar:**
1. Abra `http://<DNS-do-ALB>/` no navegador.
2. Crie o perfil (preencha nome e e-mail, no mínimo) e envie uma **foto** `image/jpeg` ou `image/png`.
3. **Edite** o perfil e salve novamente.
4. Confirme que a **foto aparece** no cartão (servida via `GET /photo`).
5. Confirme que o **`APP_NAME`** exibido na página corresponde ao valor do segredo (`AWS Profile Lab`).
6. No **CloudWatch Logs**, confirme os eventos `PROFILE_CREATED`, `PHOTO_UPLOADED`/`PHOTO_CHANGED` e `PROFILE_UPDATED`.
7. Confirme que o **Session Manager** conecta à EC2.

**Como validar:** o cartão exibe os dados e a foto; o `APP_NAME` é o do segredo; os eventos estão no log stream `app-events`; o Session Manager abre um shell.

---

## Etapa 19 — Remoção temporária da rota `0.0.0.0/0 -> NAT`

**O que fazer:** remover temporariamente a rota `0.0.0.0/0 -> NAT-LAB` da route table privada (`RT-PRIV`), validar o comportamento e depois **restaurar** a rota.

**Por que fazer:** este é o experimento central do laboratório. Ele prova que os **VPC Endpoints bastam** para a aplicação funcionar, independentemente do NAT: S3 e DynamoDB (Gateway Endpoints) e Secrets Manager, CloudWatch Logs e SSM/Session Manager (Interface Endpoints) continuam acessíveis, enquanto a saída geral para a internet deixa de funcionar.

**Dependências:** todas as etapas anteriores concluídas e validadas (Etapa 18).

**O que selecionar/executar no Console e na EC2:**
1. VPC > *Route tables* > `RT-PRIV` > **Routes** > **Edit routes** > **remova** a linha `0.0.0.0/0 -> nat-...` > salvar.
2. No navegador, repita o teste da Etapa 18: criar/editar perfil, enviar foto, ver `APP_NAME`, confirmar eventos no CloudWatch, e conectar via Session Manager. **Tudo deve continuar funcionando.**
3. Dentro da EC2 (Session Manager), confirme que o acesso geral à internet parou:
   ```bash
   sudo dnf update   # deve FALHAR / travar por timeout (sem rota para a internet)
   ```
4. Restaure a rota: VPC > `RT-PRIV` > **Edit routes** > adicionar novamente `0.0.0.0/0 -> NAT-LAB` > salvar.

**Como validar:** com a rota removida, a aplicação segue 100% funcional (endpoints), mas `sudo dnf update` falha. Após restaurar a rota, `sudo dnf update` volta a funcionar.

---

# Endurecimento (documentado, não aplicar automaticamente)

As políticas abaixo são **exemplos documentados**. **Não as aplique automaticamente** durante a montagem inicial — faça isso **manualmente, somente após validar** que os IDs reais dos endpoints (`vpce-...`) estão corretos. Aplicá-las cedo demais pode **bloquear o próprio acesso administrativo** (inclusive pelo Console).

## Endpoint Policy restritiva — Gateway Endpoint do S3 (só o bucket)

Restringe o que passa pelo Gateway Endpoint do S3 ao bucket do laboratório:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    "Resource": ["arn:aws:s3:::<bucket-do-lab>", "arn:aws:s3:::<bucket-do-lab>/*"]
  }]
}
```

## Endpoint Policy restritiva — Gateway Endpoint do DynamoDB (só a tabela `profiles`)

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
    "Resource": ["arn:aws:dynamodb:us-east-1:<account-id>:table/profiles"]
  }]
}
```

## Bucket Policy — exigir acesso pelo VPC Endpoint (`aws:SourceVpce`)

Recusa qualquer acesso ao bucket que **não** venha pelo Gateway Endpoint do S3 do laboratório. **Substitua `vpce-xxxxxxxxxxxxxxxxx`** pelo ID real do seu Gateway Endpoint do S3 (Etapa 11) **antes de aplicar**:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AcessoSomenteViaVpcEndpoint",
    "Effect": "Deny",
    "Principal": "*",
    "Action": "s3:*",
    "Resource": [
      "arn:aws:s3:::<bucket-do-lab>",
      "arn:aws:s3:::<bucket-do-lab>/*"
    ],
    "Condition": {
      "StringNotEquals": { "aws:SourceVpce": "vpce-xxxxxxxxxxxxxxxxx" }
    }
  }]
}
```

> **Atenção:** só aplique esta Bucket Policy **após validar o `vpce` real** do Gateway Endpoint do S3. Aplicá-la com o `vpce` errado ou antes da infraestrutura estar completa pode bloquear o acesso ao bucket, inclusive pelo Console.

## IAM Role vs Bucket Policy vs Endpoint Policy

Três mecanismos atuam em camadas diferentes, e o acesso efetivo é a **interseção** das três (a chamada só é permitida se **todas** permitirem):

| Mecanismo | Onde se aplica | O que controla | Pergunta que responde |
|-----------|----------------|----------------|------------------------|
| **IAM Role (identidade)** | Na EC2 (quem faz a chamada) | O que a *identidade* pode fazer e em quais recursos | "Esta instância pode chamar `s3:GetObject` neste bucket?" |
| **Bucket Policy (recurso)** | No bucket S3 | Quem/por qual caminho pode acessar o *recurso* | "Este bucket aceita requisições vindas deste VPC Endpoint?" |
| **Endpoint Policy (caminho de rede)** | No VPC Endpoint | Quais ações/recursos podem passar *por aquele endpoint* | "Este endpoint deixa passar chamadas para este bucket/tabela?" |

---

# Solução de problemas

| Sintoma | Causas prováveis | Como investigar / corrigir |
|---------|------------------|-----------------------------|
| **Health check unhealthy** no Target Group | App não está rodando na porta 5000; `SG-EC2` não libera 5000 vindo de `SG-ALB`; health check path diferente de `/health` | Na EC2: `curl http://localhost:5000/health` deve retornar 200. Confirme a regra inbound 5000 de `SG-ALB` em `SG-EC2` e o path `/health` no Target Group. |
| **502 Bad Gateway** na aplicação | Dependência AWS indisponível (DynamoDB/Secrets/S3) por endpoint ou IAM Role; app caiu | Veja o evento `ERROR` no CloudWatch Logs. Confirme os Gateway Endpoints (rota em `RT-PRIV`), o Interface Endpoint do Secrets Manager e as permissões da `ROLE-EC2-LAB`. |
| **Foto não aparece** no cartão | Falha no `s3:GetObject`; Gateway Endpoint do S3 ausente/sem rota; `BUCKET_NAME` errado em `config.py`; `photoKey` não persistido | Confirme o Gateway Endpoint do S3 e a rota da prefix list em `RT-PRIV`. Verifique `BUCKET_NAME`. A rota `GET /photo` retorna 404 quando não há `photoKey`. |
| **Logs não aparecem** no CloudWatch | Interface Endpoint `logs` ausente/sem DNS privado; `SG-INTERFACE-ENDPOINTS` não libera 443 de `SG-EC2`; falta permissão de Logs na Role | A falha de log não bloqueia a app (é tolerada), por isso pode passar despercebida. Confirme o endpoint `logs`, o SG 443 e as permissões `logs:*` da Role. |
| **Session Manager não conecta** | Faltam os Interface Endpoints `ssm`/`ssmmessages`/`ec2messages` (ou DNS privado desabilitado); Role sem `AmazonSSMManagedInstanceCore`; `SG-INTERFACE-ENDPOINTS` sem 443 de `SG-EC2` | Confirme os três endpoints do SSM com DNS privado, o `SG-INTERFACE-ENDPOINTS` liberando 443 a partir de `SG-EC2`, e a política `AmazonSSMManagedInstanceCore` na `ROLE-EC2-LAB`. |

---

> **Lembrete de escopo:** este guia descreve apenas passos **manuais** no Console AWS. Os entregáveis do projeto são código da aplicação, arquivos de configuração e esta documentação — **nenhum recurso AWS é provisionado por automação**.
