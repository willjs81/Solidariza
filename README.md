# Solidariza — Sistema Multi-ONG

Solidariza é um painel web para gestão solidária com múltiplas ONGs e controle granular de permissões. O sistema permite cadastrar beneficiários, famílias, eventos, registrar presenças, gerenciar distribuições e controlar estoque por ONG, além de relatórios com filtros avançados.

## Funcionalidades principais
- Multi-ONG com papéis e permissões
  - Admin Global: acesso irrestrito à rede; pode selecionar qualquer ONG ou "Toda a Rede"
  - Admin da ONG: gerencia a própria ONG (colaboradores, estoque, distribuições)
  - Manager: operacional na ONG (estoque, distribuições, eventos)
  - User: leitura (sem criar/editar)
- Estoque por ONG
  - Produtos são de uma ONG específica (único por nome dentro da ONG)
  - Movimentações (entrada/saída) só podem ocorrer dentro da ONG do produto
  - Distribuições checam coerência: produto e beneficiário devem pertencer à ONG
  - Visão "Toda a Rede" é agregada e somente leitura
- Beneficiários e Famílias (com criação de dependentes e lógica para menor de idade)
- Distribuições (regra de 30 dias por produto/beneficiário)
- Eventos e Presenças
- Relatórios com filtros por ONG, CPF/ID/nome, eventos, período
- Seletor de organização ativa na sidebar

## Estrutura do projeto
- Django 5 (Python 3.12)
- App principal: `panel`
- Modelos centrais: `Organization`, `Beneficiary`, `Product`, `StockMovement`, `Distribution`, `Event`, `Attendance`, `Family`, `FamilyMember`
- Middleware: organização ativa via sessão
- Frontend: Bulma + `panel.css`

## Requisitos
- Python 3.12+
- Pip / venv
- (Opcional) Postgres em produção

## Setup (desenvolvimento local)
Windows PowerShell (exemplo):

```powershell
# 1) Criar e ativar venv
python -m venv .venv
& .\.venv\Scripts\Activate.ps1

# 2) Instalar dependências
pip install -r Solidariza/requirements.txt

# 3) Migrar e iniciar
python Solidariza\manage.py migrate
python Solidariza\manage.py createsuperuser
.\.venv\Scripts\python.exe Solidariza\manage.py runserver 0.0.0.0:8000
```

Acesso: `http://localhost:8000`

## Organização ativa na sessão
- Admin Global pode escolher: uma ONG específica ou "Toda a Rede" (somente leitura)
- Usuários comuns operam sempre na própria ONG

## Permissões (resumo)
- Admin Global: tudo
- Admin ONG / Manager: estoque, distribuições, eventos na ONG
- User: somente leitura

## Estoque por ONG (detalhes técnicos)
- `Product.organization` define a qual ONG o produto pertence
- `StockMovement.clean/save` garante que `movement.organization == product.organization`
- `Distribution.clean/save` garante organização do produto e vínculo do beneficiário com a ONG
- `deliver_basket` valida coerência, checa regra de 30 dias e registra saída + distribuição

## Branches e Fluxo Git
- Branches:
  - `main`: produção
  - `homolog`: homologação
  - `dev`: desenvolvimento
  - Features: `feature/<nome>` (abre PR para `dev`)

Sugestão de fluxo:
```bash
git checkout dev
git pull
git checkout -b feature/minha-feature
# ...edite o código...
git commit -m "minha feature"
git push -u origin feature/minha-feature
# Abra um PR para dev
```

## CI/CD (GitHub Actions)
- `.github/workflows/ci.yml`: valida o projeto (instala deps, `manage.py check`, migrações dry-run)
- `.github/workflows/deploy.yml`: build da imagem Docker e upload de artifact; seleciona ambiente por branch (`dev`, `homolog`, `main` ⇒ `prod`)

## Deploy (opções sugeridas)
- Econômico: AWS Lightsail + Docker (Nginx + Gunicorn) + DB gerenciado (ou RDS)
- Gerenciado: AWS App Runner + RDS
- Alternativas simples: Railway/Render (2 serviços: dev e prod)

### Passo a passo (prod-like no Lightsail)

1) Criar `.env.prod` em `Solidariza/.env.prod`:

```env
DJANGO_SECRET_KEY=troque-esta-chave
DJANGO_DEBUG=False
ALLOWED_HOSTS=seu-dominio.com.br,www.seu-dominio.com.br
CSRF_TRUSTED_ORIGINS=https://seu-dominio.com.br,https://www.seu-dominio.com.br
TIME_ZONE=America/Sao_Paulo

# Postgres (serviço db)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=solidariza
DATABASE_URL=postgres://postgres:postgres@db:5432/solidariza
```

2) Subir serviços:

```bash
docker compose -f Solidariza/docker-compose.prod.yml up -d --build
```

3) Criar superusuário:

```bash
docker compose -f Solidariza/docker-compose.prod.yml exec web python manage.py createsuperuser
```

4) (Opcional) Emitir TLS via webroot (Let's Encrypt):

```bash
export DOMAIN=seu-dominio.com.br
docker compose -f Solidariza/docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d $DOMAIN -d www.$DOMAIN --email admin@$DOMAIN --agree-tos --no-eff-email
docker compose -f Solidariza/docker-compose.prod.yml restart nginx
```

5) Renovação automática já configurada (serviço `certbot`).

6) Diagnóstico:

```bash
docker compose -f Solidariza/docker-compose.prod.yml ps
docker compose -f Solidariza/docker-compose.prod.yml logs -f --tail=200
```

Checklist produção:
- DEBUG=False, SECRET_KEY seguro, ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS
- Banco Postgres, storage de mídia (ex.: S3)
- Servir estáticos (Whitenoise/Nginx)
- Gunicorn com `max-requests` e healthcheck
- Logs rotacionados e monitoramento

## Licenciamento por ONG (SaaS)
- Assinatura mensal por ONG com planos (limites/uso)
- Webhooks de pagamento atualizam status da assinatura
- Middleware bloqueia operações de escrita quando vencido (leitura preservada)

## Suporte
Abra issues/PRs no repositório. Sugestões e melhorias são bem-vindas.
