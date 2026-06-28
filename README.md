# Almoxarifado — Controle de Almoxarifado e Patrimônio

Plataforma web **multiorganização (multi-tenant)** para controle de almoxarifado e
patrimônio, com hierarquia de setores, RBAC com escopo, transferências com confirmação,
compras (privadas e públicas — Lei nº 14.133/2021), documentos em PDF e auditoria.

Construída com tecnologias **100% gratuitas / open source**. Interface, mensagens e
documentação em **português do Brasil**.

> **Status atual:** Fases 0 a 4 concluídas — multi-tenant, autenticação (Argon2 + 2FA
> opcional), RBAC com escopo de setor, **hierarquia de setores e visibilidade**, cadastros
> base (categorias/localizações), **catálogo de produtos (consumível/durável) com campos
> customizáveis (JSONB) e import/export Excel**, **estoque de consumíveis** (saldos por setor,
> entrada/saída/lote transacional, movimentações append-only, alertas de estoque mínimo),
> auditoria, dashboard e UI base. As próximas fases (transferências com confirmação,
> patrimônio, compras, documentos, relatórios) seguem o roadmap em
> [`PROMPT_SISTEMA_COMERCIAL.md`](PROMPT_SISTEMA_COMERCIAL.md).

---

## ✨ Principais recursos (já disponíveis)

- 🏢 **Multi-tenant** com isolamento total por `organizacao_id` (testado).
- 🔐 **Autenticação forte:** senhas Argon2, 2FA TOTP opcional, troca de senha forçada,
  rate limiting no login, CSRF, headers de segurança (CSP/HSTS via Talisman).
- 👥 **RBAC com escopo de setor:** papéis com níveis, permissões granulares e papéis
  padrão semeados (Administrador, Gestor, Comprador/Financeiro, Operador, Consulta).
- 🌳 **Hierarquia de setores** em árvore (N níveis) com `path` materializado e regras de
  **visibilidade de estoque** entre setores (somente leitura).
- 📦 **Catálogo de produtos** (consumível por quantidade / durável serializado), SKU
  automático, foto, busca/filtros/paginação, **import/export Excel**.
- 🧩 **Campos customizáveis (JSONB)** por entidade e categoria — texto, número, data,
  sim/não, seleção única/múltipla e anexo — com validação no servidor e render dinâmico.
- 📊 **Estoque de consumíveis**: saldo por setor (com quantidade em trânsito),
  **entrada/saída/lote** em transações atômicas (saldo nunca negativo), **custo médio**
  ponderado, ajuste de inventário com justificativa, movimentações **append-only** e
  **alertas** de estoque mínimo/zerado no dashboard.
- 🧾 **Auditoria append-only** de ações sensíveis.
- 🎨 **UI white-label:** Bootstrap 5.3 + HTMX + Alpine.js, tema (logo/cores) por
  organização, sidebar colável, dashboard com gráficos (Chart.js). Tudo no padrão BR.
- 🐳 **Pronto para Docker** (app + PostgreSQL + Redis + Nginx) e para rodar localmente
  sem Docker (SQLite automático em desenvolvimento).

---

## 🧰 Stack

| Camada | Tecnologia |
|---|---|
| Linguagem / framework | Python 3.12+ · Flask 3 (factory + blueprints) |
| ORM / migrações | SQLAlchemy 2 · Flask-Migrate (Alembic) |
| Banco | PostgreSQL 16 (produção) · SQLite (dev/testes) |
| Auth / segurança | Flask-Login · Flask-WTF (CSRF) · Argon2 · pyotp (2FA) · Flask-Limiter · Talisman |
| Frontend | Bootstrap 5.3 · HTMX · Alpine.js · Chart.js (assets vendorizados localmente) |
| Infra | Redis · Gunicorn · Nginx · Docker Compose |
| Qualidade | pytest · ruff · mypy · pre-commit · GitHub Actions |

---

## 🚀 Início rápido (desenvolvimento, sem Docker)

Pré-requisitos: **Python 3.12+**. Recomendado o [uv](https://docs.astral.sh/uv/)
(rápido e isolado), mas funciona com `venv`/`pip`.

```bash
# 1. Ambiente e dependências
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Configuração (o .env já funciona com SQLite por padrão)
cp .env.example .env

# 3. Banco + dados de demonstração
export FLASK_ENV=development
flask --app wsgi db upgrade        # cria as tabelas (SQLite local)
flask --app wsgi almox seed        # cria org "demo" + admin + setores de exemplo

# 4. Subir
flask --app wsgi run --debug
```

Acesse **http://127.0.0.1:5000** e entre com:

| Campo | Valor |
|---|---|
| Usuário | `admin` |
| Senha | `Almox@2026` |

> Sem `DATABASE_URL` definida em desenvolvimento, o sistema cria automaticamente
> `instance/almoxarifado.sqlite3` — não é preciso instalar PostgreSQL para experimentar.

---

## 🐳 Instalação via Docker (produção / on-premises)

Sobe **app + PostgreSQL + Redis + Nginx** com um comando.

```bash
cp .env.example .env
# Edite o .env: defina SECRET_KEY forte e POSTGRES_PASSWORD.
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

# (opcional) criar dados de demonstração no primeiro boot:
#   SEED_DEMO=true

docker compose up -d --build
```

O container do app **aguarda o banco, aplica as migrações** (`flask db upgrade`) e
sincroniza as permissões automaticamente (ver `docker/entrypoint.sh`). A aplicação
fica disponível via Nginx em **http://localhost** (porta 80).

### Criar a primeira organização e o administrador

```bash
docker compose exec app flask --app wsgi almox criar-org --nome "Prefeitura X"
docker compose exec app flask --app wsgi almox criar-admin --org prefeitura-x \
    --nome "Maria Admin" --email maria@org.gov.br --username maria
# A senha inicial é gerada e exibida; a troca é exigida no primeiro acesso.
```

### HTTPS

Para produção na internet, configure **TLS (Let's Encrypt)** no Nginx: descomente o
bloco `443` em `docker/nginx.conf`, monte os certificados e ajuste `FORCE_HTTPS=true`
no `.env` (ativa cookies `Secure`, HSTS e redirecionamento).

---

## ⚙️ Variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `FLASK_ENV` | não | `development` | `development` \| `production` \| `testing` |
| `SECRET_KEY` | **sim (prod)** | inseguro (dev) | Chave de sessão/CSRF. Gere uma forte. |
| `DATABASE_URL` | **sim (prod)** | SQLite (dev) | Ex.: `postgresql+psycopg://user:senha@db:5432/almoxarifado` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | docker | — | Credenciais do Postgres no compose. |
| `REDIS_URL` | não | memória | Cache, rate limit e fila. Ex.: `redis://redis:6379/0` |
| `FORCE_HTTPS` | não | `false` | Cookies `Secure`, HSTS, redireciona para HTTPS. |
| `SEED_DEMO` | não | `false` | Cria dados de demonstração no boot do container. |
| `APP_NAME` | não | `Almoxarifado` | Nome padrão (white-label da instalação). |
| `MAIL_*` | não | — | SMTP para alertas/convites. |
| `SENTRY_DSN` | não | — | Observabilidade de erros. |

---

## 🖥️ Comandos de administração (CLI)

```bash
flask --app wsgi almox seed                  # permissões + dados demo (idempotente)
flask --app wsgi almox sincronizar-permissoes
flask --app wsgi almox criar-org --nome "Cliente"
flask --app wsgi almox criar-admin --org cliente --nome "..." --email ... --username ...
flask --app wsgi almox criar-superadmin --nome "..." --email ... --username ...
```

---

## 👤 Papéis padrão

| Papel | Nível | O que faz |
|---|---|---|
| Administrador da Organização | 90 | Controle total dentro da organização |
| Gestor de Setor | 60 | Gerencia seu setor e a subárvore (cadastros, movimentações, transferências, inventário) |
| Comprador / Financeiro | 50 | Pedidos, fornecedores, notas fiscais, entradas valoradas |
| Operador | 30 | Movimentações, empréstimos e recebimentos no seu escopo |
| Consulta | 10 | Somente leitura |

O administrador pode criar papéis próprios e ajustar permissões por organização.

---

## 🧪 Testes e qualidade

```bash
pytest                 # testes + cobertura
ruff check .           # lint
ruff format .          # formatação
mypy app               # checagem de tipos
pre-commit install     # ganchos de git (lint/format/mypy automáticos)
```

A **CI no GitHub Actions** roda lint, formatação, mypy e testes (contra PostgreSQL)
em cada push/PR — ver `.github/workflows/ci.yml`.

---

## 🗂️ Estrutura do projeto

```
app/
├── __init__.py          # create_app(): config, extensões, blueprints, segurança
├── config.py            # config por ambiente (SQLite dev / Postgres prod)
├── extensions.py        # db, migrate, login, csrf, limiter, cache, mail
├── models/              # SQLAlchemy (organizacao, usuario, rbac, setor, auditoria)
├── services/            # regras de negócio (setup/seed, ...)
├── routes/              # blueprints finos (auth, main)
├── forms/               # WTForms
├── security/            # RBAC, permissões, auditoria
├── templates/           # Jinja2 (base, layout_app, auth, dashboard)
├── static/              # css/js + vendor (Bootstrap/HTMX/Alpine/Chart.js)
├── utils/               # formatação BR, etc.
└── cli.py               # comandos almox
migrations/              # Alembic
tests/                   # pytest
docker/                  # entrypoint + nginx.conf
docker-compose.yml · Dockerfile · pyproject.toml
```

---

## 🔄 Atualização de versão

```bash
git pull
docker compose build app
docker compose up -d        # o entrypoint aplica `flask db upgrade` automaticamente
```

Em desenvolvimento: `flask --app wsgi db upgrade`.

---

## 💾 Backup e restauração (PostgreSQL)

```bash
# Backup
docker compose exec db pg_dump -U almox almoxarifado > backup_$(date +%F).sql

# Restauração
cat backup_2026-06-28.sql | docker compose exec -T db psql -U almox -d almoxarifado
```

Recomenda-se agendar `pg_dump` (cron) com retenção e cópia externa.

---

## 🔒 Segurança e conformidade

- HTTPS obrigatório em produção (`FORCE_HTTPS=true` + TLS no Nginx).
- Senhas Argon2; 2FA TOTP opcional; troca de senha inicial forçada.
- CSRF em todos os formulários; CSP/HSTS/X-Frame-Options via Talisman.
- Isolamento multi-tenant em toda consulta; auditoria append-only.
- **LGPD:** dados pessoais mínimos; trilha de auditoria; política de retenção.

---

## 📦 Modelos de implantação

- **SaaS** multi-tenant: uma instalação atende várias organizações.
- **On-premises**: uma organização por instalação, via Docker no servidor do cliente.

Ambos a partir do mesmo código, via configuração.

---

## 📄 Licença e créditos

Software proprietário. Construído sobre bibliotecas open source — Flask, SQLAlchemy,
Bootstrap, HTMX, Alpine.js, Chart.js, Argon2, entre outras. Consulte as licenças
respectivas de cada dependência.
