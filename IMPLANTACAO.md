# Guia de Implantação Manual no Console AWS — `IMPLANTACAO.md`

Passo a passo **manual** para montar toda a infraestrutura do laboratório **AWS VPC Endpoints** no **Console AWS**, na região **`us-east-1`**. A aplicação roda em uma **única EC2 privada** (sem alta disponibilidade). A única exceção à "AZ única" é a **segunda subnet pública**, criada apenas porque o Application Load Balancer (ALB) exige subnets em **duas Availability Zones distintas** — ela não hospeda recursos de aplicação.

> **Importante:** nenhum recurso é criado por automação. Todos os passos abaixo são executados manualmente no Console AWS. A aplicação em execução é o próprio teste do laboratório.

## Convenções e valores de referência

Os nomes e valores abaixo vêm de `app/config.py` e devem ser usados exatamente como estão (exceto `BUCKET_NAME`, que é um placeholder único a definir por você):

| Item | Valor |
|------|-------|
| Região | `us-east-1` |
| VPC CIDR (sugerido) | `10.0.0.0/16` |
| Subnet pública A (sugerida) | `10.0.1.0/24` em `us-east-1a` |
| Subnet privada (sugerida) | `10.0.2.0/24` em `us-east-1a` |
| Subnet pública B (sugerida, só para o ALB) | `10.0.3.0/24` em `us-east-1b` |
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

### Nomes (tags `Name`) de todos os recursos

Defina as tags `Name` exatamente como abaixo para facilitar a navegação no Console. O padrão de nomenclatura é **MAIÚSCULAS com hífen** (`TIPO-FUNCAO`), seguindo o estilo já existente no projeto.

**Rede e segurança (já definidos no projeto):**

| Recurso | Nome (tag `Name`) |
|---------|-------------------|
| VPC | `VPC-LAB` |
| Subnet pública A | `SUBNET-PUB-A` |
| Subnet privada | `SUBNET-PRIV` |
| Subnet pública B (só para o ALB) | `SUBNET-PUB-B` |
| Internet Gateway | `IGW-LAB` |
| Route table pública | `RT-PUB` |
| Route table privada | `RT-PRIV` |
| NAT Gateway | `NAT-LAB` |
| Security Group do ALB | `SG-ALB` |
| Security Group da EC2 | `SG-EC2` |
| Security Group dos Interface Endpoints | `SG-INTERFACE-ENDPOINTS` |
| IAM Role da EC2 | `ROLE-EC2-LAB` |

> **Nota sobre a renomeação:** a subnet pública original passa a se chamar `SUBNET-PUB-A` (antes `SUBNET-PUB`), para formar um par claro com a nova `SUBNET-PUB-B`. A subnet privada continua `SUBNET-PRIV`.

**Recursos de computação, balanceamento e endpoints (nomes definidos neste guia):**

| Recurso | Nome (tag `Name`) |
|---------|-------------------|
| Instância EC2 (aplicação) | `EC2-APP-LAB` |
| Application Load Balancer | `ALB-LAB` |
| Target Group do ALB | `TG-APP-5000` |
| Gateway Endpoint do S3 | `VPCE-S3` |
| Gateway Endpoint do DynamoDB | `VPCE-DYNAMODB` |
| Interface Endpoint do Secrets Manager | `VPCE-SECRETSMANAGER` |
| Interface Endpoint do CloudWatch Logs | `VPCE-LOGS` |
| Interface Endpoint do SSM | `VPCE-SSM` |
| Interface Endpoint do SSM Messages | `VPCE-SSMMESSAGES` |
| Interface Endpoint do EC2 Messages | `VPCE-EC2MESSAGES` |

---

## Etapa 1 — VPC

**O que criar:** uma VPC chamada `VPC-LAB` com CIDR `10.0.0.0/16`.

**Por que criar:** é a rede isolada onde todos os demais recursos (subnets, EC2, endpoints) vão residir. Define o espaço de endereçamento privado do laboratório.

**Dependências:** nenhuma. É o primeiro recurso.

**Passo a passo no Console:**
1. Acesse **Console AWS > VPC** e confirme a região **`us-east-1`** (canto superior direito).
2. No menu lateral, clique em **Your VPCs** e depois no botão **Create VPC**.
3. Em *Resources to create*, selecione **VPC only** (vamos criar subnets, IGW e rotas manualmente, para fins didáticos).
4. *Name tag*: `VPC-LAB`.
5. *IPv4 CIDR block*: selecione **IPv4 CIDR manual input** e informe `10.0.0.0/16`.
6. *IPv6 CIDR block*: **No IPv6 CIDR block** (padrão).
7. *Tenancy*: **Default** (padrão).
8. Clique em **Create VPC**.

**Como validar:** a VPC `VPC-LAB` aparece na lista com estado **Available** e CIDR `10.0.0.0/16`.

![Descrição da imagem](<imagens/imagem%20(4).png>)

---

## Etapa 2 — Subnets (2 públicas + 1 privada)

**O que criar:** três subnets dentro da `VPC-LAB`:
- `SUBNET-PUB-A` — `10.0.1.0/24` — AZ `us-east-1a` — **pública**.
- `SUBNET-PRIV` — `10.0.2.0/24` — AZ `us-east-1a` — **privada** (hospeda a EC2 e os Interface Endpoints).
- `SUBNET-PUB-B` — `10.0.3.0/24` — AZ `us-east-1b` — **pública**, criada **somente para satisfazer o requisito do ALB** (duas AZs).

**Por que criar:** separar o ponto de entrada da internet (ALB e NAT na subnet pública) do servidor de aplicação (EC2 e Interface Endpoints na subnet privada). A `SUBNET-PUB-B` existe **apenas** porque um Application Load Balancer exige subnets em **duas Availability Zones distintas** (Etapa 16). Ela não recebe EC2, NAT nem endpoints — toda a aplicação continua em AZ única (`us-east-1a`).

> **Escopo:** isso **não** transforma o laboratório em arquitetura Multi-AZ. A EC2 continua única e privada em `us-east-1a`; a `SUBNET-PUB-B` é um pré-requisito técnico do ALB, nada mais.

**Dependências:** Etapa 1 (VPC).

**Passo a passo no Console:**
1. **VPC > Subnets > Create subnet**.
2. *VPC ID*: selecione `VPC-LAB`.
3. **Subnet 1 — pública A:**
   - *Subnet name*: `SUBNET-PUB-A`.
   - *Availability Zone*: `us-east-1a`.
   - *IPv4 subnet CIDR block*: `10.0.1.0/24`.
4. Clique em **Add new subnet** e crie a **Subnet 2 — privada:**
   - *Subnet name*: `SUBNET-PRIV`.
   - *Availability Zone*: `us-east-1a` (mesma AZ da pública A).
   - *IPv4 subnet CIDR block*: `10.0.2.0/24`.
5. Clique em **Add new subnet** e crie a **Subnet 3 — pública B (para o ALB):**
   - *Subnet name*: `SUBNET-PUB-B`.
   - *Availability Zone*: **`us-east-1b`** (AZ **diferente**, obrigatório para o ALB).
   - *IPv4 subnet CIDR block*: `10.0.3.0/24`.
6. Clique em **Create subnet**.
7. Habilite IP público automático **apenas nas subnets públicas** (necessário para o NAT; o ALB atribui seus próprios IPs):
   - Selecione `SUBNET-PUB-A` > **Actions > Edit subnet settings** > marque **Enable auto-assign public IPv4 address** > **Save**.
   - Repita para `SUBNET-PUB-B`.
   - **Não** habilite isso em `SUBNET-PRIV`.

**Como validar:** as três subnets aparecem **Available**; `SUBNET-PUB-A` e `SUBNET-PRIV` em `us-east-1a`, `SUBNET-PUB-B` em `us-east-1b`, todas em `VPC-LAB`. As duas públicas têm *auto-assign public IPv4* habilitado; a privada não.

![Descrição da imagem](<imagens/imagem%20(5).png>)

---

## Etapa 3 — Internet Gateway

**O que criar:** um Internet Gateway `IGW-LAB` anexado à `VPC-LAB`.

**Por que criar:** fornece a saída/entrada da internet para as subnets públicas (necessário para o ALB público e para a rota de saída do NAT Gateway).

**Dependências:** Etapa 1 (VPC).

**Passo a passo no Console:**
1. **VPC > Internet gateways > Create internet gateway**.
2. *Name tag*: `IGW-LAB`.
3. Clique em **Create internet gateway**.
4. Com o `IGW-LAB` selecionado, clique em **Actions > Attach to VPC**.
5. *Available VPCs*: selecione `VPC-LAB` e clique em **Attach internet gateway**.

**Como validar:** o `IGW-LAB` aparece com estado **Attached** e associado à `VPC-LAB`.

![Descrição da imagem](<imagens/imagem%20(7).png>)
---

## Etapa 4 — Route Tables

**O que criar:** duas route tables na `VPC-LAB`:
- `RT-PUB` (pública): rota `0.0.0.0/0 -> IGW-LAB`, associada a **`SUBNET-PUB-A` e `SUBNET-PUB-B`**.
- `RT-PRIV` (privada): rota `0.0.0.0/0 -> NAT-LAB` (o NAT é criado na Etapa 5), associada à `SUBNET-PRIV`.

**Por que criar:** o roteamento define o comportamento de rede. As subnets públicas alcançam a internet diretamente pelo IGW; a subnet privada só alcança a internet por meio do NAT (saída, nunca entrada). A `RT-PRIV` será o palco do exercício final (Etapa 19).

**Dependências:** Etapa 1 (VPC), Etapa 2 (subnets), Etapa 3 (IGW). A rota do NAT em `RT-PRIV` só pode ser concluída depois da Etapa 5.

**Passo a passo no Console:**
1. **VPC > Route tables > Create route table** — crie a primeira:
   - *Name*: `RT-PUB`; *VPC*: `VPC-LAB` > **Create route table**.
2. Repita para criar `RT-PRIV` (mesma VPC).
3. **Configurar `RT-PUB`:**
   - Selecione `RT-PUB` > aba **Routes** > **Edit routes** > **Add route**: *Destination* `0.0.0.0/0`, *Target* **Internet Gateway > `IGW-LAB`** > **Save changes**.
   - Aba **Subnet associations** > **Edit subnet associations** > marque **`SUBNET-PUB-A`** e **`SUBNET-PUB-B`** > **Save associations**.
4. **Configurar `RT-PRIV`:**
   - Selecione `RT-PRIV` > aba **Subnet associations** > **Edit subnet associations** > marque **`SUBNET-PRIV`** > **Save associations**.
   - A rota `0.0.0.0/0 -> NAT-LAB` será adicionada **após a Etapa 5** (aba **Routes** > **Edit routes** > **Add route**: *Destination* `0.0.0.0/0`, *Target* **NAT Gateway > `NAT-LAB`**).

**Como validar:** `SUBNET-PUB-A` e `SUBNET-PUB-B` estão associadas à `RT-PUB` (com rota para o `IGW-LAB`); `SUBNET-PRIV` está associada à `RT-PRIV`. Após a Etapa 5, a `RT-PRIV` mostra a rota `0.0.0.0/0 -> nat-...`.

![Descrição da imagem](<imagens/imagem%20(6).png>)
---

## Etapa 5 — NAT Gateway + Elastic IP

**O que criar:** um NAT Gateway `NAT-LAB` na **subnet pública A** (`SUBNET-PUB-A`), com um Elastic IP alocado.

**Por que criar:** permite que a EC2 na subnet privada faça **saída** para a internet (instalar pacotes com `dnf`/`pip`) **antes** de os endpoints estarem completos. No exercício final (Etapa 19), a rota para o NAT é removida para comprovar que os endpoints bastam.

**Dependências:** Etapa 2 (`SUBNET-PUB-A`), Etapa 3 (IGW anexado).

**Passo a passo no Console:**
1. **VPC > NAT gateways > Create NAT gateway**.
2. *Name*: `NAT-LAB`.
3. *Subnet*: `SUBNET-PUB-A`.
4. *Connectivity type*: **Public**.
5. *Elastic IP allocation ID*: clique em **Allocate Elastic IP** para alocar e associar um EIP.
6. Clique em **Create NAT gateway**.
7. Quando o NAT ficar **Available**, volte à Etapa 4 e conclua a rota `0.0.0.0/0 -> NAT-LAB` em `RT-PRIV`.

**Como validar:** o `NAT-LAB` fica **Available** com um Elastic IP associado; a `RT-PRIV` passa a conter a rota `0.0.0.0/0 -> nat-...`.
![Descrição da imagem](<imagens/imagem%20(8).png>)
![Descrição da imagem](<imagens/imagem%20(9).png>)
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

**Passo a passo no Console:**
1. **VPC > Security groups > Create security group** (repita três vezes, sempre em *VPC* = `VPC-LAB`), criando `SG-ALB`, `SG-EC2` e `SG-INTERFACE-ENDPOINTS` (preencha *Security group name* e *Description*). Deixe as regras para o passo seguinte.
2. **Editar `SG-ALB`:**
   - Aba **Inbound rules > Edit inbound rules > Add rule**: *Type* **HTTP**, *Port* `80`, *Source* **Anywhere-IPv4** (`0.0.0.0/0`) > **Save rules**.
   - Aba **Outbound rules > Edit outbound rules**: remova o "All traffic" padrão se desejar restringir e **Add rule**: *Type* **Custom TCP**, *Port* `5000`, *Destination* **Custom** = `SG-EC2` > **Save rules**.
3. **Editar `SG-EC2`:**
   - Aba **Inbound rules > Edit inbound rules > Add rule**: *Type* **Custom TCP**, *Port* `5000`, *Source* **Custom** = `SG-ALB` > **Save rules**. **Não** adicione nenhuma regra de SSH (porta 22).
   - Aba **Outbound rules > Edit outbound rules > Add rule**: *Type* **HTTPS**, *Port* `443`, *Destination* **Custom** = `SG-INTERFACE-ENDPOINTS`. Mantenha também uma saída `443` geral (`0.0.0.0/0`) enquanto o NAT existir (necessária para o registro inicial do SSM Agent e instalação de pacotes) > **Save rules**.
4. **Editar `SG-INTERFACE-ENDPOINTS`:**
   - Aba **Inbound rules > Edit inbound rules > Add rule**: *Type* **HTTPS**, *Port* `443`, *Source* **Custom** = `SG-EC2` > **Save rules**.
   - *Outbound*: mantenha o padrão.

**Como validar:** cada SG mostra exatamente as regras acima. Confirme que `SG-EC2` **não** possui regra de entrada na porta 22.
![Descrição da imagem](<imagens/imagem%20(10).png>)
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

**Passo a passo no Console:**
1. **Console AWS > IAM > Roles > Create role**.
2. *Trusted entity type*: **AWS service**.
3. *Use case*: **EC2** > **Next**.
4. Em *Add permissions*, procure e marque a política gerenciada **`AmazonSSMManagedInstanceCore`** > **Next**.
5. *Role name*: `ROLE-EC2-LAB` > **Create role**.
6. Abra a role `ROLE-EC2-LAB` > aba **Permissions > Add permissions > Create inline policy** > aba **JSON** e cole as políticas de exemplo abaixo (substitua os placeholders `<...>`). Você pode criar uma política inline por serviço ou unificá-las em uma só.
7. O Console cria o **Instance Profile** de mesmo nome automaticamente ao associar a role a uma EC2.

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
![Descrição da imagem](<imagens/imagem%20(12).png>)

**Como validar:** a Role `ROLE-EC2-LAB` existe, possui as policies acima e a `AmazonSSMManagedInstanceCore`, e tem um Instance Profile associado (visível na criação da EC2 na Etapa 14).
![Descrição da imagem](<imagens/imagem%20(11).png>)
---

## Etapa 8 — S3 bucket privado

**O que criar:** um bucket S3 **privado** com nome único (ex.: `aws-vpc-endpoints-lab-SEU-SUFIXO`), **Block Public Access habilitado** e **sem** hospedagem de site estático.

**Por que criar:** armazena a foto do perfil (objeto `profiles/profile-001/avatar.jpg`). O bucket é privado porque a foto é servida apenas pela aplicação (proxy via `GET /photo`), garantindo que o acesso ao S3 passe pelo Gateway Endpoint.

**Dependências:** nenhuma técnica, mas o nome do bucket deve ser definido antes da instalação da app (Etapa 15), pois precisa ser ajustado em `config.py`.

**Passo a passo no Console:**
1. **Console AWS > S3 > Create bucket**.
2. *AWS Region*: **US East (N. Virginia) us-east-1**.
3. *Bucket name*: seu nome **único global** (ex.: `aws-vpc-endpoints-lab-SEU-SUFIXO`).
4. *Object Ownership*: **ACLs disabled** (padrão).
5. *Block Public Access settings*: mantenha **Block all public access** marcado (ON).
6. *Bucket Versioning*: **Disable** (padrão, suficiente para o lab).
7. **Não** habilite *Static website hosting*.
8. Clique em **Create bucket**.

**Como validar:** o bucket aparece com *Access: Bucket and objects not public*. **Lembre-se de ajustar `BUCKET_NAME` em `app/config.py`** com este nome (atualmente o placeholder é `aws-vpc-endpoints-lab-REPLACE-ME`) — ver Etapa 15.

![Descrição da imagem](<imagens/imagem%20(13).png>)
---

## Etapa 9 — DynamoDB tabela `profiles`

**O que criar:** uma tabela DynamoDB chamada `profiles` com chave primária (partition key) `profileId` do tipo **String**.

**Por que criar:** armazena os dados do perfil (nome, e-mail, profissão, cidade, bio, interesses, `photoKey`, `updatedAt`). O design separa dados (DynamoDB) de imagem (S3).

**Dependências:** nenhuma.

**Passo a passo no Console:**
1. **Console AWS > DynamoDB > Tables > Create table**.
2. *Table name*: `profiles`.
3. *Partition key*: `profileId`, tipo **String**.
4. *Sort key*: deixe **em branco** (não usar).
5. *Table settings*: **Customize settings**.
6. *Table class*: **DynamoDB Standard** (padrão).
7. *Read/write capacity settings*: **On-demand**.
8. Clique em **Create table**.

**Como validar:** a tabela `profiles` fica **Active**, com partition key `profileId (String)`.
![Descrição da imagem](<imagens/imagem%20(14).png>)
---

## Etapa 10 — Secrets Manager (segredo da aplicação)

**O que criar:** um segredo chamado `aws-vpc-endpoints-lab/app-config` com o conteúdo:
```json
{"APP_NAME":"AWS Profile Lab","APP_ENV":"lab"}
```

**Por que criar:** a aplicação lê o `APP_NAME` deste segredo via Interface Endpoint do Secrets Manager e o exibe na página, demonstrando o uso de um Interface Endpoint.

**Dependências:** nenhuma.

**Passo a passo no Console:**
1. **Console AWS > Secrets Manager > Store a new secret**.
2. *Secret type*: **Other type of secret**.
3. Em *Key/value pairs*, mude para a aba **Plaintext** e cole o JSON acima (ou cadastre os pares `APP_NAME` = `AWS Profile Lab` e `APP_ENV` = `lab`).
4. *Encryption key*: **aws/secretsmanager** (padrão) > **Next**.
5. *Secret name*: `aws-vpc-endpoints-lab/app-config` > **Next**.
6. *Automatic rotation*: **desabilitada** (não necessária no laboratório) > **Next** > **Store**.

**Como validar:** o segredo aparece com o nome exato e, ao **Retrieve secret value**, mostra `APP_NAME` e `APP_ENV`.
![Descrição da imagem](<imagens/imagem%20(15).png>)
---

## Etapa 11 — Gateway Endpoint do S3 (`VPCE-S3`)

**O que criar:** um VPC Endpoint do tipo **Gateway** para o serviço `com.amazonaws.us-east-1.s3`, associado à **route table privada** (`RT-PRIV`), com tag `Name` = `VPCE-S3`.

**Por que criar:** permite que a EC2 na subnet privada acesse o S3 **sem** passar pela internet/NAT. É um dos protagonistas do laboratório (tipo Gateway).

**Dependências:** Etapa 1 (VPC), Etapa 4 (`RT-PRIV`).

**Passo a passo no Console:**
1. **VPC > Endpoints > Create endpoint**.
2. *Name tag*: `VPCE-S3`.
3. *Type* / *Service category*: **AWS services**.
4. Em *Services*, pesquise por **`s3`** e selecione a entrada **`com.amazonaws.us-east-1.s3`** com **Type: Gateway**.
5. *VPC*: `VPC-LAB`.
6. *Route tables*: marque **`RT-PRIV`**.
7. *Policy*: **Full access** nesta fase (a restrição fica para a seção de Endurecimento).
8. Clique em **Create endpoint**.

**Como validar:** o endpoint `VPCE-S3` fica **Available** e a `RT-PRIV` passa a mostrar uma rota para a **prefix list** do S3 (`pl-...`) apontando para o endpoint (`vpce-...`). **Observe que não há Security Group associado** — Gateway Endpoints são controlados por rota.

![Descrição da imagem](<imagens/imagem%20(16).png>)
![Descrição da imagem](<imagens/imagem%20(18).png>)
---

## Etapa 12 — Gateway Endpoint do DynamoDB (`VPCE-DYNAMODB`)

**O que criar:** um VPC Endpoint do tipo **Gateway** para o serviço `com.amazonaws.us-east-1.dynamodb`, associado à **route table privada** (`RT-PRIV`), com tag `Name` = `VPCE-DYNAMODB`.

**Por que criar:** permite que a EC2 acesse a tabela `profiles` sem internet/NAT. Segundo Gateway Endpoint do laboratório.

**Dependências:** Etapa 1 (VPC), Etapa 4 (`RT-PRIV`).

**Passo a passo no Console:**
1. **VPC > Endpoints > Create endpoint**.
2. *Name tag*: `VPCE-DYNAMODB`.
3. *Service category*: **AWS services**.
4. Pesquise por **`dynamodb`** e selecione **`com.amazonaws.us-east-1.dynamodb`** com **Type: Gateway**.
5. *VPC*: `VPC-LAB`.
6. *Route tables*: marque **`RT-PRIV`**.
7. *Policy*: **Full access** nesta fase.
8. Clique em **Create endpoint**.

**Como validar:** o endpoint `VPCE-DYNAMODB` fica **Available** e a `RT-PRIV` mostra a rota da **prefix list** do DynamoDB apontando para o `vpce-...`. Novamente, **sem Security Group**.
![Descrição da imagem](<imagens/imagem%20(17).png>)
---

## Etapa 13 — Interface Endpoints (Secrets Manager, Logs e SSM)

**O que criar:** cinco Interface Endpoints (AWS PrivateLink), todos na **subnet privada** (`SUBNET-PRIV`), com **DNS privado habilitado** e Security Group **`SG-INTERFACE-ENDPOINTS`**:

| Serviço a pesquisar | Nome do serviço | Tag `Name` do endpoint |
|---------------------|-----------------|------------------------|
| `secretsmanager` | `com.amazonaws.us-east-1.secretsmanager` | `VPCE-SECRETSMANAGER` |
| `logs` | `com.amazonaws.us-east-1.logs` | `VPCE-LOGS` |
| `ssm` | `com.amazonaws.us-east-1.ssm` | `VPCE-SSM` |
| `ssmmessages` | `com.amazonaws.us-east-1.ssmmessages` | `VPCE-SSMMESSAGES` |
| `ec2messages` | `com.amazonaws.us-east-1.ec2messages` | `VPCE-EC2MESSAGES` |

**Por que criar:** permitem que a aplicação acesse Secrets Manager e CloudWatch Logs, e que o **Session Manager** funcione (`ssm`, `ssmmessages`, `ec2messages`) em uma EC2 **sem** acesso à internet. Diferente dos Gateway Endpoints, **cada Interface Endpoint cria uma ENI com IP privado na subnet, usa Security Group e se comunica via PrivateLink na porta 443**.

**Dependências:** Etapa 2 (`SUBNET-PRIV`), Etapa 6 (`SG-INTERFACE-ENDPOINTS`).

**Passo a passo no Console (repita para cada um dos cinco serviços):**
1. **VPC > Endpoints > Create endpoint**.
2. *Name tag*: use o nome da tabela acima (ex.: `VPCE-SECRETSMANAGER`).
3. *Service category*: **AWS services**.
4. Em *Services*, pesquise pelo termo da coluna "Serviço a pesquisar" e selecione a entrada correspondente com **Type: Interface**.
5. *VPC*: `VPC-LAB`.
6. *Subnets*: marque a AZ `us-east-1a` e selecione a subnet **`SUBNET-PRIV`** (AZ única — não selecione outra AZ).
7. *Enable DNS name* (Private DNS): **marcado** (habilitado).
8. *Security groups*: selecione **`SG-INTERFACE-ENDPOINTS`** (desmarque o `default` se vier selecionado).
9. *Policy*: **Full access** nesta fase.
10. Clique em **Create endpoint**.

![Descrição da imagem](<imagens/imagem%20(19).png>)
![Descrição da imagem](<imagens/imagem%20(20).png>)

**Como validar:** cada Interface Endpoint fica **Available**, mostra uma **ENI** com IP privado na `SUBNET-PRIV`, tem o `SG-INTERFACE-ENDPOINTS` associado e *Private DNS* habilitado. A partir da EC2 (após a Etapa 14), `nslookup secretsmanager.us-east-1.amazonaws.com` deve resolver para um IP privado `10.0.2.x`.

---

## Etapa 14 — EC2 (`EC2-APP-LAB`, Amazon Linux 2023, sem IP público)

**O que criar:** uma instância EC2 chamada **`EC2-APP-LAB`** (ex.: `t3.micro`) com **Amazon Linux 2023**, **sem IP público**, na **subnet privada** (`SUBNET-PRIV`), com o **Instance Profile** da Etapa 7 (`ROLE-EC2-LAB`) e o Security Group `SG-EC2`. **Sem par de chaves / sem SSH**; o acesso será apenas por **Session Manager**.

**Por que criar:** é o servidor que roda a aplicação Flask. Fica em subnet privada e sem IP público para não ser acessível diretamente da internet; o acesso administrativo é feito por Session Manager pelos Interface Endpoints do SSM.

**Dependências:** Etapa 2 (`SUBNET-PRIV`), Etapa 6 (`SG-EC2`), Etapa 7 (Instance Profile), Etapa 13 (endpoints do SSM para o Session Manager funcionar sem internet). O NAT (Etapa 5) ainda deve estar ativo nesta fase para instalar pacotes.

**Passo a passo no Console:**
1. **Console AWS > EC2 > Instances > Launch instances**.
2. *Name*: `EC2-APP-LAB`.
3. *Application and OS Images (AMI)*: **Amazon Linux 2023** (arquitetura 64-bit x86).
4. *Instance type*: `t3.micro` (ou `t3.small`).
5. *Key pair (login)*: selecione **Proceed without a key pair (Not recommended)** — sem SSH.
6. *Network settings* > **Edit**:
   - *VPC*: `VPC-LAB`.
   - *Subnet*: `SUBNET-PRIV`.
   - *Auto-assign public IP*: **Disable**.
   - *Firewall (security groups)*: **Select existing security group** > `SG-EC2`.
7. *Advanced details* > *IAM instance profile*: selecione **`ROLE-EC2-LAB`**.
8. Clique em **Launch instance**.

**Como validar:** a instância `EC2-APP-LAB` fica **Running** sem IP público. Em **EC2 > Instances > selecionar a instância > Connect > Session Manager**, o botão **Connect** fica habilitado e abre um shell (confirma que o SSM Agent se registrou pelos endpoints/NAT). Se o Session Manager não conectar, verifique a Role (`AmazonSSMManagedInstanceCore`) e os endpoints `ssm`/`ssmmessages`/`ec2messages`.

---

## Etapa 15 — Instalação e configuração da aplicação na EC2

**O que criar/fazer:** instalar, **configurar o `BUCKET_NAME`** e iniciar a aplicação Flask **dentro da EC2**, acessando por **Session Manager**.

**Por que criar:** colocar a aplicação em execução na porta `5000`, pronta para ser registrada no Target Group do ALB (Etapa 16).

**Dependências:** Etapa 14 (EC2 acessível por Session Manager), NAT ativo (Etapa 5) para instalar pacotes, e `BUCKET_NAME` já definido (Etapa 8).

### 15.1 — Conectar e baixar o projeto

- **EC2 > Instances > `EC2-APP-LAB` > Connect > Session Manager > Connect**.
- Dentro da EC2:

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
```

### 15.2 — ⚠️ PASSO OBRIGATÓRIO: ajustar o `BUCKET_NAME` ANTES de iniciar o Flask

A aplicação **não funcionará corretamente** (upload/exibição de foto) enquanto o `BUCKET_NAME` estiver com o valor placeholder. **Antes de iniciar o serviço**, edite `app/config.py` e substitua o placeholder pelo nome real do bucket criado na Etapa 8.

- Valor atual (placeholder) em `config.py`:
  ```python
  BUCKET_NAME = "aws-vpc-endpoints-lab-REPLACE-ME"
  ```
- Substitua `aws-vpc-endpoints-lab-REPLACE-ME` pelo **nome exato do seu bucket** (ex.: `aws-vpc-endpoints-lab-SEU-SUFIXO`):
  ```python
  BUCKET_NAME = "aws-vpc-endpoints-lab-SEU-SUFIXO"
  ```
- Edite com `nano` ou `vi`:
  ```bash
  nano config.py   # localize a linha BUCKET_NAME e troque o valor; Ctrl+O para salvar, Ctrl+X para sair
  ```
- Confirme que o valor foi gravado corretamente:
  ```bash
  grep BUCKET_NAME config.py   # deve exibir o nome real do bucket, NUNCA REPLACE-ME
  ```

> Os demais valores de `config.py` (`TABLE_NAME`, `SECRET_NAME`, `LOG_GROUP`, `LOG_STREAM`, `AWS_REGION`, `PROFILE_ID`, `PHOTO_KEY`, `APP_PORT`) já correspondem aos recursos criados neste guia e normalmente **não** precisam ser alterados.

### 15.3 — Instalar dependências e iniciar

```bash
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

**Como validar:** dentro da EC2, `curl http://localhost:5000/health` retorna `OK` (HTTP 200). Com `systemd`, `sudo systemctl status profile-app` mostra **active (running)**. Confirme também, com `grep BUCKET_NAME config.py`, que o bucket real foi gravado.

---

## Etapa 16 — ALB público (`ALB-LAB`) e Target Group (`TG-APP-5000`)

**O que criar:** um Application Load Balancer **público** chamado **`ALB-LAB`**, usando as **duas subnets públicas** em **duas AZs distintas**, com um **Target Group** HTTP chamado **`TG-APP-5000`** na porta `5000`, *health check path* `/health`, a EC2 `EC2-APP-LAB` registrada, e um **listener HTTP 80** encaminhando para o Target Group.

**Por que criar:** é o ponto de entrada público da aplicação. Encaminha o tráfego HTTP 80 da internet para a porta `5000` da EC2 privada. O ALB exige **duas subnets em AZs distintas** — por isso usamos `SUBNET-PUB-A` (`us-east-1a`) e `SUBNET-PUB-B` (`us-east-1b`), criadas na Etapa 2.

**Dependências:** Etapa 2 (`SUBNET-PUB-A` e `SUBNET-PUB-B`), Etapa 6 (`SG-ALB`), Etapa 14 (`EC2-APP-LAB`), Etapa 15 (app rodando na porta 5000).

**Passo a passo no Console:**
1. **EC2 > Load Balancers > Create load balancer** > em **Application Load Balancer**, clique em **Create**.
2. *Load balancer name*: `ALB-LAB`.
3. *Scheme*: **Internet-facing**.
4. *IP address type*: **IPv4**.
5. *Network mapping*:
   - *VPC*: `VPC-LAB`.
   - *Mappings*: marque **`us-east-1a` > `SUBNET-PUB-A`** e **`us-east-1b` > `SUBNET-PUB-B`** (as duas AZs são obrigatórias).
6. *Security groups*: selecione **`SG-ALB`** (remova o `default`).
7. *Listeners and routing*: *Protocol* **HTTP**, *Port* **80**. Em *Default action*, clique em **Create target group** (abre nova aba):
   - *Target type*: **Instances**.
   - *Target group name*: `TG-APP-5000`.
   - *Protocol / Port*: **HTTP** / **5000**.
   - *VPC*: `VPC-LAB`.
   - *Health checks*: *Protocol* **HTTP**, *Path* **`/health`** > **Next**.
   - *Register targets*: selecione a instância **`EC2-APP-LAB`**, defina *Ports for the selected instances* = `5000`, clique em **Include as pending below** > **Create target group**.
8. Volte à aba do ALB, atualize a lista de Target Groups e selecione **`TG-APP-5000`** como ação padrão do listener HTTP 80.
9. Clique em **Create load balancer**.
![Descrição da imagem](<imagens/imagem%20(22).png>)

**Como validar:** em **EC2 > Target Groups > `TG-APP-5000` > Targets**, o alvo `EC2-APP-LAB` aparece como **healthy** (pode levar 1–2 minutos). Abrir `http://<DNS-do-ALB>/` no navegador exibe o formulário de criação de perfil (ou o cartão, se já criado). Se ficar **unhealthy**, confira a seção de Solução de problemas (porta 5000, `SG-EC2`, path `/health`).

> **Sem HTTPS/ACM:** o laboratório usa apenas o listener **HTTP 80**. Não adicione listener 443 nem certificado ACM.

![Descrição da imagem](<imagens/imagem%20(21).png>)
---

## Etapa 17 — CloudWatch Logs

**O que criar/verificar:** o log group `/aws-vpc-endpoints-lab/app` com o log stream `app-events`, criados automaticamente pela aplicação na inicialização.

**Por que criar:** a aplicação emite eventos de domínio (`APPLICATION_STARTED`, `PROFILE_CREATED`, `PROFILE_UPDATED`, `PHOTO_UPLOADED`, `PHOTO_CHANGED`, `ERROR`) via Interface Endpoint do CloudWatch Logs, permitindo observar o comportamento pelos logs.

**Dependências:** Etapa 7 (permissões de Logs na Role), Etapa 13 (`VPCE-LOGS`), Etapa 15 (app em execução).

**Passo a passo no Console:**
1. **Console AWS > CloudWatch > Logs > Log groups**.
2. Pesquise por **`/aws-vpc-endpoints-lab/app`** e abra o log group.
3. Abra o log stream **`app-events`**.

**Como validar:** o log group existe e o stream `app-events` contém pelo menos o evento `APPLICATION_STARTED` (gerado no startup) e, após usar a aplicação, eventos como `PROFILE_CREATED`.

![Descrição da imagem](<imagens/imagem%20(23).png>)

---

![Descrição da imagem](<imagens/imagem%20(24).png>)


<p align="center">
  <img src="imagens/imagem%20(28).png" width="30%" />
  <img src="imagens/imagem%20(25).png" width="30%" />
  <img src="imagens/imagem%20(26).png" width="30%" />
</p>
<p align="center">
  <img src="imagens/imagem%20(27).png" width="30%" />
</p>

## Etapa 18 — Teste funcional

**O que fazer:** validar a aplicação de ponta a ponta pelo DNS do ALB.

**Por que fazer:** confirmar que todas as integrações (DynamoDB, S3, Secrets Manager, CloudWatch Logs) e o acesso administrativo (Session Manager) funcionam antes do exercício final.

**Dependências:** Etapas 8 a 17 concluídas.

**Passo a passo:**
1. Abra `http://<DNS-do-ALB>/` no navegador (o DNS está em **EC2 > Load Balancers > `ALB-LAB` > DNS name**).
2. Crie o perfil (preencha nome e e-mail, no mínimo) e envie uma **foto** `image/jpeg` ou `image/png`.
3. **Edite** o perfil e salve novamente.
4. Confirme que a **foto aparece** no cartão (servida via `GET /photo`).
5. Confirme que o **`APP_NAME`** exibido na página corresponde ao valor do segredo (`AWS Profile Lab`).
6. No **CloudWatch Logs**, confirme os eventos `PROFILE_CREATED`, `PHOTO_UPLOADED`/`PHOTO_CHANGED` e `PROFILE_UPDATED`.
7. Confirme que o **Session Manager** conecta à EC2 `EC2-APP-LAB`.

**Como validar:** o cartão exibe os dados e a foto; o `APP_NAME` é o do segredo; os eventos estão no log stream `app-events`; o Session Manager abre um shell.

---

## Etapa 19 — Remoção temporária da rota `0.0.0.0/0 -> NAT` (experimento central)

**O que fazer:** remover temporariamente a rota `0.0.0.0/0 -> NAT-LAB` da route table privada (`RT-PRIV`), validar que a aplicação continua funcionando pelos VPC Endpoints e que a internet geral deixa de funcionar, e depois **restaurar** a rota.

**Por que fazer:** este é o experimento central do laboratório. Ele prova que os **VPC Endpoints bastam** para a aplicação funcionar, independentemente do NAT: S3 e DynamoDB (Gateway Endpoints) e Secrets Manager, CloudWatch Logs e SSM/Session Manager (Interface Endpoints) continuam acessíveis, enquanto a saída geral para a internet deixa de funcionar.

**Dependências:** todas as etapas anteriores concluídas e validadas (Etapa 18).

**Passo a passo no Console e na EC2:**

1. **Remover a rota do NAT:** **VPC > Route tables > `RT-PRIV` > Routes > Edit routes** > **remova** a linha `0.0.0.0/0 -> nat-...` > **Save changes**.

2. **Validar que os VPC Endpoints continuam funcionando** (a aplicação deve seguir 100% operacional). No navegador, pelo DNS do `ALB-LAB`:
   - **Abra o site** `http://<DNS-do-ALB>/` — o cartão/formulário deve carregar normalmente (prova DynamoDB + Secrets Manager pelos endpoints).
   - **Edite o perfil** (`/edit`), altere algum campo e salve — deve persistir (prova DynamoDB).
   - **Envie/troque a foto** — o upload e a exibição devem funcionar (prova S3 pelo Gateway Endpoint).
   - **Verifique o CloudWatch Logs** — devem surgir novos eventos `PROFILE_UPDATED` e `PHOTO_CHANGED` no stream `app-events` (prova CloudWatch Logs pelo Interface Endpoint).
   - **Feche e abra uma nova sessão do Session Manager** na `EC2-APP-LAB` — deve conectar normalmente (prova `ssm`/`ssmmessages`/`ec2messages` pelos Interface Endpoints, sem internet).

3. **Confirmar que a internet geral parou** (dentro da EC2, via Session Manager):
   ```bash
   # Teste 1 (existente): atualizacao de pacotes deve FALHAR / travar por timeout
   sudo dnf update

   # Teste 2 (novo): requisicao HTTPS a um site externo deve dar TIMEOUT
   curl -I https://example.com --connect-timeout 5
   ```
   **Esperado:** `sudo dnf update` falha/trava por timeout e o `curl -I https://example.com --connect-timeout 5` **retorna timeout** (sem resposta HTTP), porque não há mais rota para a internet. Isso comprova que **não existe** saída geral — apenas os caminhos dos VPC Endpoints seguem ativos.

4. **Restaurar a rota do NAT:** **VPC > Route tables > `RT-PRIV` > Routes > Edit routes** > **Add route**: *Destination* `0.0.0.0/0`, *Target* **NAT Gateway > `NAT-LAB`** > **Save changes**.

**Como validar:** com a rota removida, a aplicação segue 100% funcional (site abre, perfil edita, foto troca, logs aparecem, Session Manager conecta), mas `sudo dnf update` falha e `curl -I https://example.com --connect-timeout 5` dá timeout. Após restaurar a rota, `sudo dnf update` e o `curl` voltam a funcionar.

---

# Endurecimento (documentado, não aplicar automaticamente)

As políticas abaixo são **exemplos documentados**. **Não as aplique automaticamente** durante a montagem inicial — faça isso **manualmente, somente após validar** que os IDs reais dos endpoints (`vpce-...`) estão corretos. Aplicá-las cedo demais pode **bloquear o próprio acesso administrativo** (inclusive pelo Console).

## Endpoint Policy restritiva — Gateway Endpoint do S3 (`VPCE-S3`, só o bucket)

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

## Endpoint Policy restritiva — Gateway Endpoint do DynamoDB (`VPCE-DYNAMODB`, só a tabela `profiles`)

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

Recusa qualquer acesso ao bucket que **não** venha pelo Gateway Endpoint do S3 do laboratório. **Substitua `vpce-xxxxxxxxxxxxxxxxx`** pelo ID real do seu Gateway Endpoint do S3 (`VPCE-S3`, Etapa 11) **antes de aplicar**:

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
| **Health check unhealthy** no Target Group `TG-APP-5000` | App não está rodando na porta 5000; `SG-EC2` não libera 5000 vindo de `SG-ALB`; health check path diferente de `/health` | Na EC2: `curl http://localhost:5000/health` deve retornar 200. Confirme a regra inbound 5000 de `SG-ALB` em `SG-EC2` e o path `/health` no Target Group. |
| **502 Bad Gateway** na aplicação | Dependência AWS indisponível (DynamoDB/Secrets/S3) por endpoint ou IAM Role; app caiu | Veja o evento `ERROR` no CloudWatch Logs. Confirme os Gateway Endpoints (rota em `RT-PRIV`), o Interface Endpoint do Secrets Manager (`VPCE-SECRETSMANAGER`) e as permissões da `ROLE-EC2-LAB`. |
| **Foto não aparece** no cartão | Falha no `s3:GetObject`; Gateway Endpoint do S3 ausente/sem rota; `BUCKET_NAME` ainda com `REPLACE-ME` em `config.py`; `photoKey` não persistido | Confirme o Gateway Endpoint do S3 (`VPCE-S3`) e a rota da prefix list em `RT-PRIV`. Rode `grep BUCKET_NAME config.py` e verifique se é o bucket real. A rota `GET /photo` retorna 404 quando não há `photoKey`. |
| **Logs não aparecem** no CloudWatch | Interface Endpoint `logs` (`VPCE-LOGS`) ausente/sem DNS privado; `SG-INTERFACE-ENDPOINTS` não libera 443 de `SG-EC2`; falta permissão de Logs na Role | A falha de log não bloqueia a app (é tolerada), por isso pode passar despercebida. Confirme o endpoint `VPCE-LOGS`, o SG 443 e as permissões `logs:*` da Role. |
| **Session Manager não conecta** | Faltam os Interface Endpoints `ssm`/`ssmmessages`/`ec2messages` (ou DNS privado desabilitado); Role sem `AmazonSSMManagedInstanceCore`; `SG-INTERFACE-ENDPOINTS` sem 443 de `SG-EC2` | Confirme `VPCE-SSM`, `VPCE-SSMMESSAGES` e `VPCE-EC2MESSAGES` com DNS privado, o `SG-INTERFACE-ENDPOINTS` liberando 443 a partir de `SG-EC2`, e a política `AmazonSSMManagedInstanceCore` na `ROLE-EC2-LAB`. |

---

> **Lembrete de escopo:** este guia descreve apenas passos **manuais** no Console AWS. Os entregáveis do projeto são código da aplicação, arquivos de configuração e esta documentação — **nenhum recurso AWS é provisionado por automação**.
