# PROMPT — Sistema de Controle de Almoxarifado / Patrimônio (produto comercial)

> **Como usar este documento:** entregue-o inteiro a um agente de desenvolvimento (Claude,
> ChatGPT, Gemini etc.). Ele descreve **o que construir, com quais tecnologias, com quais
> regras de negócio e em qual ordem**. Usa **somente ferramentas gratuitas / open source**.
> O resultado deve ser um software **vendável, multiorganização, configurável e seguro**,
> rodando em **servidor conectado à internet**.
>
> Existe um sistema-pai já em produção (Flask + SQLite, monoinstalação) cujas regras de
> negócio servem de base. Este prompt **evolui** aquele sistema para um produto comercial.
> Toda a interface, mensagens e documentação para o usuário final: **português do Brasil**.

---

## 1. Visão geral e objetivo do produto

Construa uma **plataforma web de controle de almoxarifado e patrimônio** que possa ser
**vendida e instalada para diferentes clientes (organizações)**. Cada organização gerencia
seus próprios itens, do mais simples (ex.: papel higiênico, sem código nenhum) ao mais
complexo (bem durável com código de tombamento, número de série, marca, modelo, garantia).

Princípios que orientam **todas** as decisões:

1. **Flexível e configurável** — o cliente cadastra suas próprias categorias, unidades,
   tipos de item, **campos customizáveis** e modelos de documento sem precisar de programação.
2. **Multiorganização (multi-tenant)** — uma instalação atende várias organizações com
   **isolamento total de dados**. Dentro de cada organização há uma **hierarquia de setores**.
3. **Seguro por padrão** — autenticação forte, RBAC, auditoria completa, proteção contra as
   vulnerabilidades comuns (OWASP Top 10).
4. **Rastreável** — todo movimento gera trilha de auditoria imutável e, quando aplicável,
   um **documento** (saída, recebimento, devolução, transferência, baixa) armazenado.
5. **Performático** — paginação, índices, consultas eficientes, cache onde fizer sentido.
6. **Vendável** — white-label (logo/cores/nome por organização), licenciamento por plano,
   onboarding simples e **README excelente**.

---

## 2. Glossário do domínio (leia antes de modelar)

- **Organização (tenant):** o cliente que comprou o sistema. Raiz do isolamento de dados.
- **Setor / Unidade:** nó da hierarquia interna da organização. Tem **3 níveis**:
  - **Setor principal (central/órgão):** controle global. Recebe dos fornecedores e
    **distribui** para setores secundários **ou** direto para usuários finais.
  - **Setor secundário:** recebe do principal e distribui para terciários/usuários finais.
  - **Setor terciário / usuário final:** ponta da cadeia, consome ou guarda o item.
  - Modele como **árvore** (cada setor tem `setor_pai_id`), não com 3 tabelas fixas — assim
    suporta 1, 2, 3 ou mais níveis sem refatorar.
- **Item / Produto (catálogo):** a *definição* de um material (nome, categoria, unidade,
  campos customizados). NÃO é a quantidade física.
- **Tipo de controle do item** (decisão central de modelagem):
  - **CONSUMÍVEL (por quantidade):** controlado por saldo numérico (ex.: papel, caneta,
    material de limpeza). Quando é "pago para uso", **dá baixa e encerra a ação** — resta só o
    histórico para métricas. Não há código por unidade.
  - **DURÁVEL / PATRIMÔNIO (por unidade serializada):** cada exemplar é **único e rastreável**
    individualmente (tombamento, nº de série, marca, modelo, estado de conservação, garantia).
    É "pago para uso" mas continua sob controle: **revisado/cobrado periodicamente** (ex.:
    inventário anual de status), pode **retornar ao setor principal** e ser **destinado a
    outro lugar**.
- **Saldo de estoque (`SaldoEstoque`):** quantidade de um item consumível **em um setor**.
  O mesmo item pode ter saldos diferentes em setores diferentes.
- **Ativo (`Ativo` / unidade patrimonial):** cada exemplar individual de um item durável,
  com seu próprio ciclo de vida e **setor/portador atual**.
- **Movimentação:** todo evento que altera saldo ou localização (entrada, saída, transferência,
  empréstimo, devolução, baixa, ajuste de inventário).
- **Transferência (com confirmação):** envio de material de um setor para outro em **duas
  etapas** — o setor de origem **envia e confere**; o material fica **em trânsito** e o
  recebimento no destino fica **pendente** até o setor de destino **receber, conferir e
  confirmar**. Pode haver **divergência** (item faltou/sobrou/chegou avariado) e o **setor
  superior que enviou pode corrigir** a transferência. Ver §7.8.
- **Em trânsito:** quantidade/ativo que já saiu da origem mas ainda não foi confirmado no
  destino — não conta no saldo de nenhum dos dois setores como disponível.
- **Documento:** comprovante emitido e armazenado de uma movimentação (PDF + metadados).
- **Inventário (recontagem/recertificação):** processo periódico em que se confere fisicamente
  saldos (consumíveis) e o status/estado de cada ativo durável (a "cobrança anual").

---

## 3. Stack tecnológica recomendada (tudo gratuito / open source)

Como agora roda em **servidor na internet** e será **vendido**, suba o nível em relação ao
sistema-pai (que usa SQLite local). Stack recomendada:

| Camada | Tecnologia | Por quê |
|---|---|---|
| Linguagem | **Python 3.12+** | Continuidade com o sistema-pai (Flask). |
| Framework | **Flask 3** (factory + blueprints) | Já dominado; maduro. *Alternativa:* FastAPI se quiser API-first. |
| ORM / migrações | **SQLAlchemy 2 + Flask-Migrate (Alembic)** | Migrações de verdade (nada de `ALTER TABLE` manual). |
| Banco | **PostgreSQL 16** | Concorrência real, `JSONB` (campos customizados), índices GIN, RLS opcional, backup robusto. SQLite **não** serve para servidor multiusuário. |
| Auth sessão | **Flask-Login** + **Flask-WTF (CSRF)** | Sessão + proteção CSRF. |
| Senhas | **Argon2** (`argon2-cffi`) | Mais forte que o hash padrão; *fallback* Werkzeug/PBKDF2. |
| 2FA | **pyotp** (TOTP) + QR | Segundo fator opcional por usuário/organização. |
| Permissões | RBAC próprio (ver §8) | Papéis + escopo por setor. |
| Forms/validação | **Flask-WTF / WTForms** + validação server-side | Nunca confiar no cliente. |
| Frontend | **Bootstrap 5.3** + **HTMX** + **Alpine.js** + JS vanilla | Sem build pesado; interatividade sem React/Vue. |
| Selects com busca | **Tom Select** | Já usado no sistema-pai. |
| Gráficos | **Chart.js** | Dashboards. |
| Excel | **openpyxl** | Import/export. |
| PDF | **WeasyPrint** (HTML→PDF) | Documentos e recibos com layout HTML/CSS. |
| QR / código de barras | **qrcode** + **python-barcode** | Etiquetas de tombamento/SKU. |
| Tarefas assíncronas | **APScheduler** (simples) ou **Celery + Redis** (escala) | Alertas, inventário, e-mails. |
| Cache / fila | **Redis** | Cache, rate limit, sessões, Celery. |
| E-mail | **SMTP** (Flask-Mail) | Alertas/convites; provedor gratuito. |
| Rate limiting | **Flask-Limiter** | Anti força-bruta/abuso. |
| Servidor app | **Gunicorn** (+ workers) | Produção. *Windows:* `waitress`. |
| Proxy reverso | **Nginx** + **TLS (Let's Encrypt)** | HTTPS obrigatório. |
| Empacotamento | **Docker + docker-compose** | Instalação reproduzível no cliente. |
| Testes | **pytest** + **pytest-cov** + **factory_boy** | Cobrir regras de negócio. |
| Qualidade | **ruff** (lint+format) + **mypy** + **pre-commit** | Padrão de código. |
| CI | **GitHub Actions** | Lint + testes + build em cada push. |
| Erros/observabilidade | **Sentry (SDK self-host/free)** + logging estruturado | Diagnóstico em produção. |
| Versionamento | **Git + GitHub** | Repositório. |

**Regra:** nada de bibliotecas pagas, APIs cobradas ou serviços fechados. Se algo exigir
internet (CDN), sirva **localmente** também, mas para um produto-servidor o padrão é assets
empacotados/buildados no deploy.

---

## 4. Arquitetura

Padrão **application factory** + **blueprints**, com camada de **serviços** (regras de
negócio fora das rotas) e **repositórios/queries** isolados:

```
almoxarifado/
├── app/
│   ├── __init__.py          # create_app(): config, extensões, blueprints, error handlers
│   ├── config.py            # Config por ambiente (dev/prod/test) lendo variáveis de ambiente
│   ├── extensions.py        # db, migrate, login_manager, csrf, limiter, mail, cache
│   ├── models/              # modelos SQLAlchemy (1 arquivo por agregado)
│   ├── services/            # REGRAS DE NEGÓCIO (estoque, ativos, transferências, documentos…)
│   ├── routes/              # blueprints finos: validam input e chamam services
│   ├── forms/               # WTForms
│   ├── templates/           # Jinja2 (herança de base.html) + parciais HTMX
│   ├── static/              # css/js/vendor/uploads servidos por proxy em produção
│   ├── documents/           # geração de PDF (templates + WeasyPrint)
│   ├── security/            # RBAC, decorators, escopo de tenant/setor, auditoria
│   └── cli.py               # comandos: seed, criar-org, criar-admin, importar…
├── migrations/              # Alembic
├── tests/                   # pytest
├── docker-compose.yml       # app + postgres + redis + nginx
├── Dockerfile
├── .env.example
├── pyproject.toml           # deps + ruff + mypy
└── README.md
```

Regras de arquitetura:
- **Rotas finas, serviços gordos.** Nenhuma regra de negócio dentro de template ou rota.
- **Todo acesso a dados filtra por `organizacao_id`** (tenant) — sem exceção. Centralize isso
  (ex.: query base por sessão/usuário) para evitar vazamento entre clientes.
- **Transações atômicas:** operações que mexem em saldo/ativo + criam movimentação + emitem
  documento acontecem dentro de **uma transação**; se algo falha, faz rollback total.
- **Idempotência** em seeds, migrações e comandos de manutenção.

---

## 5. Modelo de dados (PostgreSQL + SQLAlchemy)

Use o **modelo híbrido** para flexibilidade: colunas fixas para o que é comum + coluna
**`JSONB campos` para campos customizados** definidos pelo cliente (ver §6). Resumo dos
agregados (ajuste nomes conforme o padrão do projeto):

**Organizacao** (`organizacoes`) — tenant
- id, nome, cnpj/identificador, slug, ativo, plano, logo, cores/tema, criado_em
- `config JSONB` (preferências, white-label, flags de visibilidade)

**Usuario** (`usuarios`)
- id, organizacao_id (FK), nome, email (único por organização), username, senha_hash (Argon2)
- **cargo/função** (texto livre ou FK p/ `Funcao`: ex.: Almoxarife, Gestor, Comprador, Fiscal),
  matricula/identificador funcional (opcional)
- ativo, totp_secret (2FA opcional), ultimo_acesso, criado_em
- **nível de acesso e funções** vêm dos **Papéis** atribuídos (com escopo de setor) — ver §8;
  um usuário pode ter mais de um papel e atuar em mais de um setor.

**Papel** (`papeis`) e **Permissao** (`permissoes`) — RBAC (ver §8)
- Papel: id, organizacao_id, nome, **nivel** (1..N — nível de acesso/hierarquia do papel),
  descricao; Permissao: chave (ex.: `produto.criar`)
- Tabela de associação papel↔permissão; e usuário↔papel **com escopo de setor**.
- Papéis padrão (sementes) + o cliente pode criar os seus (funções próprias da organização).

**Funcao** (`funcoes`) — opcional: catálogo de cargos/funções da organização
- id, organizacao_id, nome (ex.: Almoxarife, Comprador, Fiscal de Contrato), ativo
- (usado em `Usuario.cargo`; pode sugerir papéis padrão ao criar o usuário).

**Setor** (`setores`) — árvore hierárquica
- id, organizacao_id, nome, codigo, **setor_pai_id (FK self, nullable = raiz/principal)**
- tipo/nivel (PRINCIPAL | SECUNDARIO | TERCIARIO | derivado da árvore), ativo
- `path` materializado (ex.: `1/4/9`) para consultas de subárvore rápidas
- `permite_visualizacao_externa` (bool) — base da regra de visibilidade (ver §8.3)
- **`poder_compra` (bool)** — se o setor pode realizar compras/registrar notas (ver §7.9)
- **centro_custo** (código contábil, opcional) e **orcamento_anual** (valor, opcional)

**Categoria** (`categorias`): id, organizacao_id, nome, ativo.

**Localizacao** (`localizacoes`): id, organizacao_id, setor_id, nome, descricao
(prateleira/sala física **dentro** de um setor).

**DefinicaoCampo** (`definicoes_campo`) — campos customizados (ver §6)
- id, organizacao_id, **entidade** (PRODUTO | ATIVO | SETOR | MOVIMENTACAO…)
- chave, rotulo, tipo (TEXTO, NUMERO, DATA, BOOLEANO, SELECT, MULTISELECT, ARQUIVO)
- opcoes (JSONB, para selects), obrigatorio, ordem, ativo
- aplica_a_categoria_id (opcional: campo só aparece para certa categoria)

**Produto** (`produtos`) — definição de catálogo
- id, organizacao_id, nome, sku (gerado se vazio, único por organização), categoria_id
- **tipo_controle**: `CONSUMIVEL` | `DURAVEL`
- unidade (UN, CX, L, KG…), estoque_minimo, estoque_maximo (opcional)
- marca, modelo (úteis p/ duráveis; podem virar campos customizados)
- **valor_unitario_referencia** e **custo_medio** (atualizado a cada entrada com valor — p/
  valorar o estoque consumível)
- descricao, ativo, criado_em
- **`campos JSONB`** (valores dos campos customizados de PRODUTO)
- foto/anexos

**SaldoEstoque** (`saldos_estoque`) — só p/ CONSUMÍVEL, por setor
- id, organizacao_id, produto_id, setor_id, quantidade
- **quantidade_em_transito** (reservada em transferências enviadas e ainda não confirmadas)
- unique(produto_id, setor_id); índice por setor
- (saldo nunca é editado direto: sempre derivado/atualizado por movimentação em transação;
  disponível = quantidade − quantidade_em_transito)

**Ativo** (`ativos`) — só p/ DURÁVEL: 1 linha por exemplar físico
- id, organizacao_id, produto_id (definição), **tombamento** (único por organização, opcional)
- numero_serie, marca, modelo, data_aquisicao, valor_aquisicao, fornecedor
- garantia_ate, vida_util_meses, valor_residual (p/ depreciação opcional)
- **estado_conservacao**: BOM | REGULAR | DEFASADO | INSERVIVEL
- **status_ciclo**: EM_ESTOQUE | EM_USO | EMPRESTADO | EM_MANUTENCAO | EM_TRANSITO | BAIXADO
- **setor_atual_id** (onde está agora), **portador/usuario_responsavel** (opcional)
- ultima_revisao_em, proxima_revisao_em (a "cobrança anual")
- `campos JSONB`, criado_em, ativo

**Movimentacao** (`movimentacoes`) — trilha imutável (append-only)
- id, organizacao_id, **tipo**: ENTRADA | SAIDA | TRANSFERENCIA | EMPRESTIMO | DEVOLUCAO |
  BAIXA | AJUSTE_INVENTARIO
- produto_id (consumível) **ou** ativo_id (durável)
- quantidade (1 para ativo), origem_setor_id, destino_setor_id
- **valor_unitario, valor_total** (opcionais — preenchidos em entradas com nota fiscal)
- usuario_id (quem registrou), destinatario (quem recebeu), observacoes
- documento_id (FK, opcional), **nota_fiscal_id (FK, opcional)**, lote_id (opcional), criado_em
- **nunca** editar/excluir; correções entram como nova movimentação de AJUSTE.

**LoteMovimentacao** (`lotes_movimentacao`): agrupa várias movimentações de uma operação.

**Transferencia** (`transferencias`) — cabeçalho do fluxo de envio com confirmação
- id, organizacao_id, numero (sequencial), setor_origem_id, setor_destino_id
- **status**: `RASCUNHO` | `ENVIADA` (em trânsito, aguardando recebimento) |
  `RECEBIDA` (conferida e confirmada, sem divergência) | `RECEBIDA_COM_DIVERGENCIA` |
  `CORRIGIDA` (origem ajustou após divergência) | `CANCELADA`
- enviado_por, enviado_em, recebido_por, recebido_em, corrigido_por, corrigido_em
- observacoes_envio, observacoes_recebimento, documento_envio_id, documento_recebimento_id
- criado_em. (Gera movimentações de SAIDA na origem ao enviar e de ENTRADA no destino ao
  confirmar — ver §7.8.)

**TransferenciaItem** (`transferencia_itens`) — linhas conferidas
- id, transferencia_id, produto_id (consumível) **ou** ativo_id (durável)
- quantidade_enviada, quantidade_recebida (preenchida na conferência do destino)
- estado_recebido (p/ ativo: ok/avariado), divergencia (bool), motivo_divergencia
- quantidade_corrigida (quando a origem ajusta)

**Emprestimo** (`emprestimos`): produto/ativo, quantidade, qtd_devolvida, setor/destinatário,
data_prevista, data_devolucao, status (ATIVO | PARCIAL | DEVOLVIDO | VENCIDO), observacoes.

**Documento** (`documentos`) — comprovantes emitidos/armazenados
- id, organizacao_id, **tipo**: SAIDA | RECEBIMENTO | DEVOLUCAO | TRANSFERENCIA | BAIXA |
  TERMO_RESPONSABILIDADE | INVENTARIO
- numero (sequencial por organização/tipo/ano), data, setor_origem, setor_destino
- arquivo_pdf (caminho/blob), hash (integridade), modelo_id, dados JSONB (snapshot),
  assinado_por, criado_em. Relaciona-se com movimentação(ões).

**ModeloDocumento** (`modelos_documento`): template HTML/Jinja editável por organização
(cabeçalho, logo, campos), por tipo de documento.

**Fornecedor** (`fornecedores`) — para setores com poder de compra
- id, organizacao_id, nome/razao_social, cnpj_cpf, contato, telefone, email, endereco,
  ativo, `campos JSONB`, criado_em.

**PedidoCompra** (`pedidos_compra`) — opcional (requisição/empenho antes da compra)
- id, organizacao_id, numero, setor_id (deve ter `poder_compra`), fornecedor_id (opcional),
  status (RASCUNHO | APROVADO | EMPENHADO | CONCLUIDO | CANCELADO), valor_estimado,
  solicitante_id, aprovador_id, datas, observacoes; itens em `PedidoCompraItem`
  (produto_id, quantidade, valor_unitario_estimado).

**NotaFiscal** (`notas_fiscais`) — documento de compra/entrada armazenado
- id, organizacao_id, setor_id (com `poder_compra`), fornecedor_id
- numero, serie, chave_acesso (NF-e, 44 dígitos, opcional), data_emissao, data_entrada
- **valor_total**, valor_produtos, valor_frete, valor_impostos (opcionais)
- pedido_compra_id (opcional), **arquivo (PDF e/ou XML da NF-e)**, hash, observacoes, criado_em
- itens em **NotaFiscalItem** (produto_id/ativo_id, quantidade, valor_unitario, valor_total).
- Dar **entrada** a partir da NF gera as `Movimentacao` ENTRADA com valor e atualiza
  custo_medio do produto / valor_aquisicao do ativo.

> **Módulo de Compras Públicas (opcional, ligável por organização).**
> Defina em `Organizacao.config` o **`modo_compra`**: `PRIVADO` (só o fluxo da §7.9) ou
> `PUBLICO` (habilita licitação/empenho/contrato e as fases da despesa — §7.10, Lei nº
> 14.133/2021). As entidades abaixo só aparecem/valem no modo PÚBLICO.

**DotacaoOrcamentaria** (`dotacoes_orcamentarias`) — modo PÚBLICO
- id, organizacao_id, exercicio (ano), programa_trabalho, natureza_despesa (elemento),
  fonte_recurso, unidade_orcamentaria, valor_dotado, valor_empenhado, saldo_disponivel.

**ProcessoContratacao** (`processos_contratacao`) — licitação / contratação direta
- id, organizacao_id, numero_processo, objeto, **modalidade**: `PREGAO` | `CONCORRENCIA` |
  `CONCURSO` | `LEILAO` | `DIALOGO_COMPETITIVO` | `DISPENSA` | `INEXIGIBILIDADE`
- **procedimento_auxiliar**: `REGISTRO_DE_PRECOS` (SRP) | nenhum
- valor_estimado, setor_id (requisitante), datas (abertura, homologação), número PNCP (opcional)
- **status**: PLANEJAMENTO | PUBLICADO | EM_DISPUTA | HOMOLOGADO | DESERTO | FRACASSADO |
  REVOGADO | ANULADO | CONCLUIDO; documentos anexos (ETP, TR, edital, ata da sessão, parecer).

**AtaRegistroPrecos** (`atas_registro_precos`) e **AtaItem** — SRP (procedimento auxiliar)
- Ata: id, organizacao_id, processo_id, numero, fornecedor_id, vigencia_inicio, vigencia_fim
  (até 1 ano, prorrogável conf. lei), status.
- AtaItem: produto_id, quantidade_registrada, preco_registrado, **saldo_quantidade**
  (decrementa a cada contrato/empenho que consome a ata).

**Contrato** (`contratos`), **ContratoItem**, **TermoAditivo** — contrato administrativo
- Contrato: id, organizacao_id, numero, processo_id (ou ata_id), fornecedor_id, objeto,
  valor_global, vigencia_inicio, vigencia_fim, **fiscal_id**, **gestor_id**, garantia,
  status (VIGENTE | SUSPENSO | ENCERRADO | RESCINDIDO), anexos.
- ContratoItem: produto_id, quantidade, preco_unitario, **saldo_quantidade** / **saldo_valor**.
- TermoAditivo: tipo (PRAZO | VALOR | QUANTIDADE | APOSTILAMENTO), descricao, valor, nova_vigencia.

**Empenho** (`empenhos`) — Nota de Empenho (1ª fase da despesa)
- id, organizacao_id, numero, **tipo**: ORDINARIO | ESTIMATIVO | GLOBAL
- data, valor, dotacao_id (FK), contrato_id/ata_id/processo_id (vínculo), fornecedor_id
- **saldo_a_liquidar** (decrementa nas liquidações), status (EMITIDO | PARC_LIQUIDADO |
  LIQUIDADO | ANULADO), anexo da Nota de Empenho.

**Recebimento** (`recebimentos`) — recebimento do material (art. 140 da Lei 14.133)
- id, organizacao_id, nota_fiscal_id, empenho_id, contrato_id, setor_id
- **tipo**: PROVISORIO | DEFINITIVO; recebido_por (fiscal/comissão), data, conformidade,
  observacoes/divergências. O **recebimento definitivo** é o gatilho da entrada valorada
  no almoxarifado e da liquidação.

**Liquidacao** (`liquidacoes`) e **Pagamento** (`pagamentos`) — 2ª e 3ª fases da despesa
- Liquidacao: id, empenho_id, nota_fiscal_id, recebimento_id, valor, data, atestado_por
  (fiscal), status. Pagamento: id, liquidacao_id, valor, data, ordem_bancaria/identificador,
  status. (Podem ser registros simples para trilha e relatórios — não substituem o sistema
  financeiro oficial, mas integram a prestação de contas e o controle do almoxarifado.)

**Inventario** (`inventarios`) e **InventarioItem**: ciclo de recontagem/recertificação
(período, setor, status; por item: qtd esperada vs contada, ou estado/status do ativo,
divergências, responsável).

**Auditoria** (`auditoria`) — log de ações sensíveis
- id, organizacao_id, usuario_id, acao, entidade, entidade_id, dados_antes JSONB,
  dados_depois JSONB, ip, user_agent, criado_em. **Append-only.**

**ConfigSistema / Licenca**: chave/valor por organização; dados de licença/plano e expiração.

Índices essenciais: tudo por `organizacao_id`; `(produto_id, setor_id)` em saldos;
`tombamento`, `numero_serie`, `status_ciclo`, `setor_atual_id` em ativos; `criado_em` e
`tipo` em movimentações; GIN em colunas `JSONB campos` para busca por campo customizado.

---

## 6. Campos customizáveis (diferencial do produto)

Decisão de design: **modelo híbrido (recomendado)**.
- Atributos **comuns e consultados com frequência** = colunas fixas (nome, sku, categoria,
  estoque, tombamento, série, estado…).
- Atributos **definidos pelo cliente** = coluna **`JSONB campos`** na entidade, descritos por
  registros em **`DefinicaoCampo`**. Indexe com **GIN** para buscas.
- Evite EAV puro (3 tabelas) — gera JOINs caros e perde tipagem; JSONB no PostgreSQL resolve
  com melhor performance e queries mais simples.

Requisitos:
- Admin da organização cria/edita/ordena campos por **entidade** e, opcionalmente, por
  **categoria** (ex.: produtos da categoria "Informática" ganham campo "Processador").
- Tipos suportados: texto, número, data, booleano, seleção única, múltipla, arquivo/anexo.
- Validação dirigida pela definição (obrigatório, opções válidas, tipo) **no servidor**.
- Formulários e listas renderizam os campos dinamicamente; export/import os respeita.

---

## 7. Regras de negócio (a parte mais importante)

### 7.1 Consumível vs Durável
- **Consumível:** controlado por `SaldoEstoque` por setor. Entrada soma; saída subtrai;
  transferência move entre setores. "Pago para uso" = **SAÍDA que encerra a ação**: baixa do
  saldo do setor e registra movimentação; resta o **histórico para métricas**. Não há
  unidade individual nem código por item.
- **Durável:** cada exemplar é um `Ativo`. Quantidade sempre 1. Tem ciclo de vida (status),
  pode ser **emprestado**, **transferido**, **retornar ao setor principal** e ser
  **redestinado**. É **recertificado periodicamente** (inventário anual de status).

### 7.2 Estoque (consumível) — sempre em transação
- **Entrada:** valida qtd > 0; soma ao saldo do setor de destino; cria `Movimentacao` ENTRADA;
  emite **Documento de Recebimento**.
- **Saída/Distribuição:** bloqueia se qtd > saldo disponível no setor de origem; subtrai;
  cria SAIDA; emite **Documento de Saída**.
- **Transferência entre setores:** **não** é atômica de um passo — segue o fluxo de envio
  com confirmação em duas etapas descrito em **§7.8** (sai da origem, fica em trânsito, e só
  entra no destino após o recebimento ser conferido e confirmado). Suporta a cadeia
  **principal → secundário → terciário/usuário**.
- **Lote:** várias operações de uma vez; **valida todos antes de gravar**; se um falhar, não
  grava nada e mostra todos os erros.
- **Saldo nunca é editado à mão** — só por movimentação. Ajustes de inventário entram como
  `AJUSTE_INVENTARIO` com justificativa.

### 7.3 Ativos duráveis — ciclo de vida
- Estados (`status_ciclo`): EM_ESTOQUE → EM_USO/EMPRESTADO → (DEVOLUCAO) → EM_ESTOQUE →
  EM_MANUTENCAO → … → BAIXADO. Toda transição é uma `Movimentacao` + documento.
- **Tombamento e nº de série únicos** por organização; ao cadastrar/editar, bloquear
  duplicidade com mensagem indicando qual ativo já usa.
- **Retorno ao setor principal e redestinação:** transferir o ativo de volta ao principal
  (status EM_ESTOQUE) e depois destiná-lo a outro setor/usuário (nova transferência).
- **Recertificação anual ("cobrança"):** processo de Inventário onde, para cada ativo do
  setor, confirma-se **status_ciclo** e **estado_conservacao**, atualiza `ultima_revisao_em`
  e `proxima_revisao_em`. Alertas para ativos com revisão vencida.
- **Termo de responsabilidade:** ao destinar ativo a um usuário/setor, emitir documento de
  responsabilidade (quem responde pelo bem).
- **Depreciação (opcional):** se `valor_aquisicao` + `vida_util_meses`, calcular valor
  contábil atual (linear) para relatórios.

### 7.4 Itens inservíveis e baixa
- Ativo com `estado_conservacao = INSERVIVEL` não pode ser emprestado nem transferido para
  uso; some das listas de seleção dessas ações.
- **Baixa definitiva:** só para ativo inservível/justificado, em estoque e não emprestado.
  Marca `status_ciclo = BAIXADO`, inativa, cria `Movimentacao` BAIXA e emite **Documento de
  Baixa** (ex.: devolução a órgão competente / desfazimento). Consumível também pode ter baixa
  por perda/vencimento, com justificativa.

### 7.5 Empréstimos
- Emprestar: consumível subtrai saldo; durável muda status para EMPRESTADO. Cria `Emprestimo`
  (ATIVO) + movimentação EMPRESTIMO.
- Devolução total ou parcial (durável sempre integral): repõe saldo/estado; status vira
  PARCIAL ou DEVOLVIDO (com data); cria DEVOLUCAO. **Vencido:** ATIVO além da data prevista.
- Recibo/termo imprimível agrupado por setor.

### 7.6 Exclusão x inativação
- Só **excluir** entidade sem nenhuma movimentação/histórico. Caso contrário, **inativar**
  (soft delete via `ativo`). Histórico nunca é apagado.

### 7.7 Documentos (emissão e armazenamento)
- Toda saída, recebimento, devolução, transferência e baixa **pode gerar um documento PDF**
  numerado, armazenado e vinculado à(s) movimentação(ões).
- Numeração sequencial por organização/tipo/ano (ex.: `SAIDA-2026-000123`).
- PDF gerado de **ModeloDocumento** (HTML/Jinja editável, com logo/cabeçalho da organização).
- Guardar **hash** do PDF para integridade e um **snapshot JSONB** dos dados no momento.
- Tela para **buscar, baixar e reimprimir** documentos por tipo/período/setor.

### 7.8 Transferência entre setores com confirmação (fluxo crítico)
Transferir material **não** é um passo único. É uma máquina de estados em **duas pontas**
(origem envia/confere → destino recebe/confere/confirma), com tratamento de divergência e
correção pelo setor superior. Tudo transacional e auditado.

1. **Envio (origem):** o operador do setor de origem cria a `Transferencia` selecionando o
   setor de destino e os itens/quantidades (consumíveis) ou ativos (duráveis), e **confere**.
   Ao enviar:
   - Valida saldo/disponibilidade na origem; **reserva** a quantidade movendo-a para
     `quantidade_em_transito` (consumível) ou marcando o ativo como `EM_TRANSITO`.
   - Cria `Movimentacao` SAIDA (origem) e gera o **Documento de Saída/Guia de Transferência**.
   - Status da transferência = **ENVIADA**. O material **não entra** no destino ainda.
2. **Pendência no destino:** o setor de destino vê a transferência como **recebimento
   pendente** (notificação/alerta). Enquanto pendente, o item está **em trânsito** — não
   disponível em nenhum dos dois setores.
3. **Recebimento e conferência (destino):** o operador do destino confere fisicamente e
   informa, **por item**, a `quantidade_recebida` / estado recebido:
   - **Sem divergência** (recebido = enviado e em ordem): confirma. **No ato da confirmação o
     material já entra no estoque do destino e fica imediatamente disponível** — para
     consumível, **dá baixa do em trânsito da origem e soma ao saldo do destino**; para
     durável, muda `setor_atual_id` para o destino e `status_ciclo` para EM_ESTOQUE. Cria
     `Movimentacao` ENTRADA (destino) e emite **Documento de Recebimento**. Status = **RECEBIDA**.
   - **Com divergência** (faltou, sobrou, chegou avariado): registra o que de fato chegou e o
     **motivo**. Entra no destino **apenas o efetivamente recebido e conforme**; o restante
     fica pendente de tratamento. Status = **RECEBIDA_COM_DIVERGENCIA** e gera alerta para a
     origem/superior. O documento de recebimento registra a divergência.
4. **Correção pelo setor superior (origem):** o setor que enviou (tipicamente o superior na
   hierarquia) pode **corrigir** a transferência divergente:
   - Acertar o que de fato saiu (ex.: estornar para o saldo da origem o que não chegou por erro
     de contagem na saída, ou confirmar perda/extravio com baixa justificada), encerrando a
     pendência de em trânsito. Cria `Movimentacao` de AJUSTE com justificativa. Status =
     **CORRIGIDA**.
   - Toda correção é auditada (quem corrigiu, antes/depois, motivo). Nunca apaga histórico.
5. **Cancelamento:** enquanto **ENVIADA** e antes do recebimento, a origem pode **cancelar**,
   estornando o em trânsito de volta ao saldo/estado original. Status = **CANCELADA**.

Regras de ouro: o item em trânsito **nunca** é contado como disponível nos dois lados ao mesmo
tempo; saldo **nunca** fica negativo; cada transição grava movimentação + (quando aplicável)
documento; permissões respeitam o escopo de setor (só a origem envia/corrige; só o destino
recebe/confere).

### 7.9 Compras e controle financeiro (setores com poder de compra)
Nem todo setor compra: só os marcados com **`poder_compra`** (ex.: o órgão/setor principal e
setores autorizados). Para esses, o sistema controla **valores, fornecedores e notas fiscais**.
Esta seção é o fluxo **comum/privado**; no **modo PÚBLICO** (`Organizacao.config.modo_compra`)
ele é estendido pelo módulo de compras públicas da **§7.10**.

- **Fornecedores:** cadastro com CNPJ/CPF, contato e campos customizados.
- **Pedido de compra (opcional):** requisição/empenho antes da compra, com itens e valores
  estimados, fluxo de **aprovação** (rascunho → aprovado → empenhado → concluído) e controle
  contra o **orçamento anual** do setor (alerta/bloqueio ao estourar, configurável).
- **Nota fiscal:** ao receber a compra, registra-se a **NotaFiscal** (número, série, chave
  NF-e opcional, fornecedor, valores) e **anexa-se o arquivo (PDF e/ou XML da NF-e)**, que
  fica **armazenado** e recuperável. A entrada em estoque é gerada **a partir da NF**: cria as
  `Movimentacao` ENTRADA com `valor_unitario`/`valor_total`, vincula `nota_fiscal_id` e
  atualiza o **custo_medio** do produto (consumível) ou o **valor_aquisicao** do ativo (durável).
- **Valoração do estoque:** com os valores das entradas, o sistema calcula o **valor do
  estoque por setor/organização**, o valor do patrimônio e (opcional) a depreciação dos ativos.
- **Controle e prestação de contas:** relatórios de compras por período/fornecedor/setor,
  gasto x orçamento, e exportação (Excel/PDF). Importar XML da NF-e para preencher itens
  automaticamente é uma melhoria desejável.
- **Permissões:** apenas papéis com `compra.*` em setores com `poder_compra` registram pedidos,
  notas e entradas valoradas; demais setores seguem só com movimentação física (sem valores).

### 7.10 Compras públicas — licitação, empenho e contrato (modo PÚBLICO, Lei 14.133/2021)
Para órgãos públicos, a compra segue o rito legal e a **despesa pública tem 3 fases:
empenho → liquidação → pagamento**. A entrada do material no almoxarifado se conecta a esse
rito. Este módulo é **opcional e ligável** por organização (`modo_compra = PUBLICO`).

**Fluxo de ponta a ponta:**
1. **Requisição / planejamento:** um setor requisita; gera-se o **ProcessoContratacao** com
   objeto, valor estimado e documentos do planejamento (ETP, Termo de Referência).
2. **Seleção do fornecedor:** por **licitação** (modalidades da Lei 14.133: **pregão**
   — preferencial para bens/serviços comuns —, concorrência, concurso, leilão, diálogo
   competitivo) ou **contratação direta** (dispensa/inexigibilidade). O processo evolui de
   PLANEJAMENTO até **HOMOLOGADO** (ou deserto/fracassado/revogado/anulado). Anexar edital,
   ata da sessão e parecer.
3. **Registro de Preços (SRP), quando aplicável:** o processo gera uma **AtaRegistroPrecos**
   com itens, preços e quantidades registradas; cada compra futura **consome saldo da ata**
   (procedimento auxiliar, art. 78 — **não** é modalidade).
4. **Contrato:** formaliza-se o **Contrato** (ou nota de empenho que o substitua nos casos da
   lei), com vigência, valor global, **fiscal** e **gestor** designados, itens e saldos; admite
   **TermoAditivo** (prazo/valor/quantidade) e apostilamento. O contrato pode derivar de ata.
5. **Empenho (1ª fase):** emite-se a **Nota de Empenho** vinculada a uma **DotacaoOrcamentaria**
   (reserva o recurso: decrementa `saldo_disponivel` da dotação) e ao contrato/ata/processo.
   Tipos: ordinário, estimativo, global. O empenho passa a ter **saldo a liquidar**.
6. **Entrega e recebimento (art. 140):** o fornecedor entrega com **Nota Fiscal**; registra-se
   o **Recebimento PROVISÓRIO** (responsável pelo acompanhamento) e, após conferência de
   conformidade, o **Recebimento DEFINITIVO** pela comissão/fiscal. Divergências reaproveitam
   a lógica de conferência (falta/avaria) e podem gerar glosa/devolução ao fornecedor.
7. **Entrada no almoxarifado:** o **recebimento definitivo** é o gatilho da **entrada valorada**
   (cria `Movimentacao` ENTRADA com valor, vincula NF/empenho/contrato, atualiza custo_medio /
   valor_aquisicao) e **consome saldo** do contrato/ata e do empenho.
8. **Liquidação (2ª fase):** verifica-se o direito do credor (NF + recebimento definitivo +
   atesto do fiscal); cria-se a **Liquidacao** (decrementa `saldo_a_liquidar` do empenho).
9. **Pagamento (3ª fase):** registra-se o **Pagamento** (ordem bancária/identificador) ligado
   à liquidação. *(Liquidação/pagamento aqui servem à trilha e à prestação de contas; não
   substituem o sistema orçamentário-financeiro oficial — ofereça integração/export.)*

**Controles e regras:**
- **Saldos sempre consistentes:** dotação (dotado − empenhado), empenho (a liquidar),
  ata e contrato (quantidade/valor restantes) — nada pode ficar negativo; bloquear/alertar.
- **Fiscal e gestor de contrato** são funções (§8): só o fiscal atesta/recebe definitivamente;
  só o ordenador de despesa/gestor empenha (alçada configurável; two-person rule onde couber).
- **Rastreabilidade total:** todo item em estoque pode ser rastreado até NF → recebimento →
  empenho → contrato/ata → processo licitatório (auditoria e transparência).
- **Documentos** de cada etapa são numerados, anexados e armazenados (edital, ata, contrato,
  empenho, recebimento, liquidação) — reutiliza o subsistema de documentos (§7.7).
- **Alertas:** contratos/atas a vencer, saldo de empenho/contrato baixo, recebimentos
  pendentes de atesto, prazos legais de liquidação/pagamento.
- **Integração opcional (melhoria):** importar XML da NF-e; consultar/publicar no **PNCP**
  (Portal Nacional de Contratações Públicas) por API.

---

## 8. Hierarquia, papéis e visibilidade (RBAC com escopo)

Usuários têm **níveis de acesso** (o quanto podem fazer) **e funções** (o papel que exercem),
combinados a um **escopo de setor**. Implemente como RBAC: **Papel** (conjunto de permissões,
com um `nivel`) + **escopo (setor e subárvore)**. Um usuário pode acumular papéis e setores.

### 8.1 Papéis (sugestão; cliente pode criar os seus / mapear às suas funções)
- **SUPERADMIN (operador da plataforma):** gerencia organizações/licenças. Acima do tenant.
- **ADMIN_ORG:** controle total **dentro da sua organização** (usuários, papéis, campos,
  modelos de documento, setores, visibilidade, configurações de compra).
- **GESTOR_SETOR:** gerencia seu setor e os **descendentes** (subárvore): cadastra, movimenta,
  distribui, recebe/corrige transferências, faz inventário.
- **COMPRADOR / FINANCEIRO:** em setores com `poder_compra` — pedidos, fornecedores, notas
  fiscais, entradas valoradas, relatórios de gasto x orçamento.
- **APROVADOR:** aprova pedidos de compra (alçada por valor, opcional).
- **Funções do modo PÚBLICO (§7.10):** **AGENTE_CONTRATACAO/PREGOEIRO** (conduz a licitação),
  **GESTOR_CONTRATO** e **FISCAL_CONTRATO** (acompanham/atestam/recebem definitivamente),
  **ORDENADOR_DESPESA** (autoriza/empenha, por alçada).
- **OPERADOR:** registra movimentações/empréstimos/recebimentos no(s) setor(es) do seu escopo.
- **CONSULTA:** somente leitura.

### 8.2 RBAC com escopo de setor
- Permissões granulares por **chave**:
  - Estoque/ativos: `produto.criar`, `movimentacao.saida`, `ativo.baixar`, `inventario.realizar`…
  - Transferência: `transferencia.enviar`, `transferencia.receber`, `transferencia.corrigir`.
  - Compras (só setor com `poder_compra`): `compra.pedido`, `compra.aprovar`,
    `compra.nota_fiscal`, `compra.entrada_valorada`, `fornecedor.gerenciar`.
  - Compras públicas (modo PÚBLICO): `licitacao.gerenciar`, `ata.gerenciar`,
    `contrato.gerenciar`, `empenho.emitir`, `recebimento.definitivo`, `despesa.liquidar`,
    `despesa.pagar`, `dotacao.gerenciar`.
  - Administração: `documento.emitir`, `usuario.gerenciar`, `papel.gerenciar`, `config.campos`,
    `config.visibilidade`, `config.compras`.
- Usuário recebe **papel + escopo (setor)**; o escopo vale para o setor **e sua subárvore**
  (use o `path` materializado). Papéis de nível maior herdam as permissões relevantes.
- Decorators: `@login_required`, `@requer_permissao('chave')`, `@escopo_setor`.
- **Two-person rule** opcional para ações críticas (baixa, exclusão, export massivo, aprovação
  de compra acima de uma alçada).

### 8.3 Visibilidade de estoque entre unidades (requisito explícito)
- Por padrão, cada setor vê **apenas o próprio estoque e o de sua subárvore**.
- O **ADMIN_ORG** pode **liberar visualização cruzada**: configurar quais setores podem ver o
  estoque de quais outros (flag `permite_visualizacao_externa` no setor e/ou uma tabela de
  **regras de visibilidade** setor→setor). A visualização liberada é **somente leitura**.
- Toda query de estoque aplica: escopo do usuário **+** regras de visibilidade. Nunca confiar
  em parâmetro de URL para escolher setor — validar contra o escopo no servidor.

---

## 9. Segurança (obrigatório)

- **HTTPS** sempre (TLS via Nginx/Let's Encrypt); cookies `Secure`, `HttpOnly`, `SameSite`.
- **Senhas com Argon2**; política mínima de senha; **forçar troca** da senha inicial.
- **2FA TOTP** opcional por usuário (obrigatório configurável por organização).
- **CSRF** em todos os formulários (Flask-WTF); **proteção XSS** (escape Jinja, CSP header).
- **SQL injection:** sempre ORM/consultas parametrizadas.
- **Rate limiting** no login e endpoints sensíveis (Flask-Limiter); bloqueio progressivo.
- **Isolamento multi-tenant:** filtro por `organizacao_id` em **toda** query; testes que
  garantem que uma organização não acessa dados de outra (opcional: PostgreSQL RLS).
- **Headers de segurança** (CSP, X-Content-Type-Options, X-Frame-Options, HSTS) — ex.:
  Flask-Talisman.
- **Uploads:** validar tipo/tamanho, nomes saneados, armazenar fora do webroot.
- **Segredos** só em variáveis de ambiente / `.env` (nunca no Git). `SECRET_KEY` forte.
- **Auditoria** de ações sensíveis (quem, quando, o quê, IP) — tabela append-only.
- **LGPD:** dados pessoais mínimos, base legal, possibilidade de exportar/excluir dados de
  usuário; política de retenção.
- **Backups automáticos** do PostgreSQL (`pg_dump` agendado), testados, com retenção e cópia
  externa; documentar restauração.

---

## 10. Desempenho

- **Paginação** em todas as listas (nunca carregar tudo). Busca/filtros server-side.
- **Índices** conforme §5; evitar N+1 (use `joinedload`/`selectinload`).
- **Cache** (Redis) para dashboards/contagens e dados pouco mutáveis; invalidar em mudanças.
- **Consultas agregadas** no banco (SUM/COUNT) em vez de em Python.
- **Tarefas pesadas** (relatórios grandes, e-mails, inventário) em background (APScheduler/Celery).
- **Connection pool** do SQLAlchemy ajustado aos workers do Gunicorn.
- Metas: páginas < 300 ms em uso típico; export de milhares de linhas via streaming.

---

## 11. API (opcional, recomendado para um produto)

- API REST versionada (`/api/v1`) com autenticação por **token/JWT** ou chave de API por
  organização, respeitando RBAC e tenant. Documentada (OpenAPI/Swagger).
- Endpoints para produtos, estoque, ativos, movimentações, documentos. Habilita integrações,
  app mobile futuro e leitores de código de barras.

---

## 12. Licenciamento e modelo comercial (produto vendável)

- **Planos** (ex.: Básico/Pro/Enterprise) que habilitam recursos e limites (nº de usuários,
  setores, organizações, API, 2FA obrigatório, white-label).
- **Licença/expiração por organização** (renovável pelo SUPERADMIN), evoluindo o controle de
  expiração do sistema-pai. Aviso quando faltar pouco; bloqueio gradual ao expirar.
- **White-label:** logo, cores, nome do sistema e cabeçalho dos documentos por organização.
- **Onboarding:** assistente para criar organização, primeiro admin, setores e categorias;
  dados de exemplo opcionais.
- **Modos de implantação:** (a) **SaaS** multi-tenant (uma instalação, vários clientes);
  (b) **on-premises** (uma organização por instalação, via Docker no servidor do cliente).
  O código deve suportar ambos via configuração.

---

## 13. UX / UI

- Layout limpo: navbar + sidebar colável (mobile-first), tema por organização.
- **Dashboard:** cartões (itens, alertas de estoque mínimo/zerado, empréstimos vencidos,
  ativos com revisão vencida, **recebimentos de transferência pendentes**, **transferências
  com divergência a corrigir**, e — para setor com poder de compra — **pedidos a aprovar**,
  **gasto x orçamento**, e no modo público **contratos/atas a vencer**, **saldo de empenho
  baixo** e **recebimentos pendentes de atesto**), gráficos (Chart.js) de entradas/saídas no
  tempo, últimas movimentações.
- Listas com busca, filtros (categoria, setor, tipo, estado, alerta) e ordenação; selects com
  busca (Tom Select); ações em massa.
- Interações sem recarregar via **HTMX/Alpine** (modais de confirmação, filtros, devolução).
- Mensagens **flash** claras (success/danger/warning/info); validação amigável.
- Datas em `dd/mm/aaaa`; números/moeda no padrão BR.
- **Etiquetas com QR/código de barras** para produtos/ativos (impressão em folha).
- **Acessibilidade** básica (labels, contraste, navegação por teclado) e **responsividade**
  para conferência física no celular (considerar PWA).

---

## 14. Relatórios e métricas

- Consumo por período/setor/categoria; itens mais movimentados; curva ABC.
- Posição de estoque por setor; **valor do estoque (custo médio)**; valor total do patrimônio;
  depreciação acumulada.
- Empréstimos em aberto/vencidos; ativos por status/estado; revisões vencidas.
- **Compras:** por período/fornecedor/setor; **gasto x orçamento** (centro de custo);
  notas fiscais emitidas; pedidos pendentes de aprovação.
- **Compras públicas (modo PÚBLICO):** execução orçamentária (dotado/empenhado/liquidado/pago);
  saldos de empenho/contrato/ata; contratos e atas por vigência; processos por modalidade;
  mapa de rastreabilidade item→NF→empenho→contrato→processo (transparência/prestação de contas).
- Transferências (pendentes, recebidas, com divergência) e divergências de inventário.
- Export **Excel e PDF** em todos os relatórios.

---

## 15. Plano de ação faseado (roadmap para o agente)

Implemente em fases; ao fim de cada fase, **rode os testes** e garanta que o sistema sobe.
Faça commits pequenos e descritivos.

**Fase 0 — Fundação (esqueleto):**
1. Estrutura de pastas (§4), `pyproject.toml`, `.env.example`, `.gitignore`, `Dockerfile`,
   `docker-compose.yml` (app + postgres + redis + nginx), pre-commit (ruff/mypy).
2. `create_app()` com config por ambiente, extensões, healthcheck, error handlers, logging.
3. Conexão PostgreSQL + Flask-Migrate; migração inicial vazia; CI no GitHub Actions.

**Fase 1 — Multi-tenant, auth e RBAC:**
4. Modelos Organizacao, Usuario, Papel, Permissao, associações com escopo de setor.
5. Login (Argon2), logout, sessão, CSRF, rate limit, forçar troca de senha inicial, 2FA TOTP.
6. Decorators de permissão/escopo; filtro global por `organizacao_id`; testes de isolamento.
7. CLI: `criar-org`, `criar-admin`, `seed`.

**Fase 2 — Hierarquia de setores e cadastros base:**
8. Setor (árvore + `path`), Categoria, Localizacao, CRUD com RBAC.
9. Regras de visibilidade entre setores (§8.3) e telas de configuração.

**Fase 3 — Catálogo e campos customizáveis:**
10. Produto (tipo_controle), DefinicaoCampo, render dinâmico de `campos JSONB`, validação.
11. SKU automático; foto/anexos; import/export Excel respeitando campos customizados.

**Fase 4 — Estoque de consumíveis:**
12. SaldoEstoque por setor (com `quantidade_em_transito`); serviços de entrada, saída e lote
    (transacional).
13. Movimentacao (append-only) + LoteMovimentacao; alertas de estoque mínimo/zerado.

**Fase 4b — Transferência com confirmação (fluxo crítico, §7.8):**
13a. Transferencia + TransferenciaItem com máquina de estados (RASCUNHO→ENVIADA→
     RECEBIDA/RECEBIDA_COM_DIVERGENCIA→CORRIGIDA / CANCELADA).
13b. Envio com conferência e reserva em trânsito; pendência e alerta no destino; recebimento
     com conferência item a item; tratamento de divergência; correção pelo setor superior;
     cancelamento. Tudo transacional, auditado e com documentos. Cobrir com testes.

**Fase 5 — Ativos duráveis (patrimônio):**
14. Ativo com tombamento/série únicos, estado, status_ciclo, setor_atual, revisões.
15. Transferência/retorno ao principal/redestinação; manutenção; baixa definitiva.
16. Depreciação opcional; termo de responsabilidade.

**Fase 5b — Compras e controle financeiro (§7.9):**
16a. Setor com `poder_compra`, centro de custo e orçamento; Fornecedor; (opcional) PedidoCompra
     com aprovação por alçada e controle x orçamento.
16b. NotaFiscal com anexo de PDF/XML armazenado; entrada valorada a partir da NF (valor_unitario/
     total, custo_medio, valor_aquisicao); valoração do estoque/patrimônio. Cobrir com testes.

**Fase 5c — Compras públicas (opcional, modo PÚBLICO, §7.10):**
16c. Flag `modo_compra`; DotacaoOrcamentaria, ProcessoContratacao (modalidades), AtaRegistroPrecos,
     Contrato/Aditivos, Empenho — com controle de saldos.
16d. Fases da despesa: Recebimento provisório/definitivo (gatilho da entrada valorada),
     Liquidacao e Pagamento; funções fiscal/gestor/ordenador; rastreabilidade item→NF→empenho→
     contrato→processo; alertas de vigência/saldo/prazo. (Opcional: import XML NF-e, API PNCP.)

**Fase 6 — Empréstimos:**
17. Emprestar/devolver (total/parcial), vencidos, recibos por setor.

**Fase 7 — Documentos:**
18. ModeloDocumento (HTML/Jinja editável), geração PDF (WeasyPrint), numeração, hash, snapshot.
19. Vincular documentos às movimentações; tela de busca/download/reimpressão.

**Fase 8 — Inventário / recertificação:**
20. Inventario + itens; contagem de consumíveis; recertificação anual de ativos; divergências
    e ajustes; alertas de revisão vencida (agendados).

**Fase 9 — Dashboard, relatórios e métricas:**
21. Dashboard com cartões e gráficos; relatórios (§14) com export Excel/PDF; cache.

**Fase 10 — API, white-label e licenciamento:**
22. API REST `/api/v1` (auth por token, OpenAPI); white-label; planos/licença por organização;
    onboarding.

**Fase 11 — Endurecimento e entrega:**
23. Headers de segurança (Talisman/CSP), Sentry, auditoria completa, backups `pg_dump`
    agendados + doc de restauração.
24. Cobertura de testes das regras críticas; revisão de performance (índices, N+1).
25. **README** completo (§17), guia de instalação Docker, guia do usuário, changelog.

---

## 16. Critérios de aceite

- Uma instalação atende **várias organizações** com **isolamento total** (testado).
- Hierarquia de setores de **3+ níveis**; principal distribui a secundários/usuários,
  secundários a terciários/usuários; tudo gera movimentação e documento.
- **Transferência com confirmação em duas etapas**: ao enviar, o item fica **em trânsito** e
  o recebimento no destino fica **pendente**; só entra no destino após conferência e
  confirmação. **Ao confirmar, o material entra imediatamente no estoque do destino.**
  Divergências (falta/sobra/avaria) são registradas e o **setor superior corrige**
  a transferência; o item em trânsito nunca conta como disponível nos dois setores ao mesmo tempo.
- Cadastrar **consumível sem código** e **durável com tombamento/série/marca/modelo**.
- **Setores com poder de compra** controlam valores, cadastram fornecedores e **armazenam notas
  fiscais (PDF/XML)**; a entrada valorada atualiza custo do estoque e valor do patrimônio.
- **Modo PÚBLICO (Lei 14.133/2021), quando ligado:** licitação/contratação direta, ata de
  registro de preços, contrato (com fiscal/gestor) e empenho controlam saldos; o **recebimento
  definitivo** dispara a entrada valorada; **empenho → liquidação → pagamento** ficam
  registrados; cada item é rastreável até NF → empenho → contrato → processo.
- **Usuários têm níveis de acesso e funções** (papéis com escopo de setor), configuráveis pelo
  admin; permissões são aplicadas e auditadas.
- Consumível "pago para uso" **encerra** com baixa e deixa histórico para métricas.
- Durável é **recertificado anualmente**, pode **retornar ao principal** e ser **redestinado**.
- Admin **libera ou não** a visualização de estoque entre unidades, e a regra é respeitada.
- Saída/recebimento/devolução/transferência/baixa **emitem e armazenam documentos** (PDF
  numerado, recuperável).
- **Campos customizáveis** por entidade/categoria funcionam em formulários, listas e export.
- Tombamento/série nunca duplicam; inservível só sai por baixa; saldo nunca fica negativo.
- RBAC com escopo de setor aplicado; auditoria registra ações sensíveis.
- HTTPS, CSRF, rate limit, Argon2, 2FA opcional, backups automáticos funcionando.
- Migrações Alembic aplicam limpo em banco novo e existente. CI verde (lint + testes).
- Roda via **Docker** em servidor na internet; **zero custo de licença de software** (stack livre).

---

## 17. README (precisa ser excelente — é um produto à venda)

O README deve conter, no mínimo:
- Visão geral, principais recursos e capturas de tela.
- **Pré-requisitos** e **instalação via Docker** passo a passo (subir app+postgres+redis+nginx).
- Variáveis de ambiente (tabela completa, com exemplos seguros).
- **Primeiros passos:** criar organização, primeiro admin, setores (com/sem poder de compra),
  categorias, campos customizados, papéis/funções e usuários.
- Guia de uso por papel (admin, gestor, comprador/financeiro, operador, consulta).
- Como configurar **transferências com confirmação** e **compras** (fornecedores, notas, orçamento).
- Como ativar e usar o **modo de compras públicas** (Lei 14.133/2021): processos/licitação,
  ata de registro de preços, contratos, empenho e as fases empenho→liquidação→pagamento.
- **Backup e restauração** (pg_dump/restore) e política de retenção.
- Atualização de versão (migrações Alembic) e changelog.
- Segurança (HTTPS, 2FA, boas práticas) e conformidade (LGPD).
- Modelos de implantação (SaaS x on-premises) e licenciamento/planos.
- Solução de problemas (FAQ) e como obter suporte.
- Licença do software e créditos das bibliotecas open source usadas.

---

## 18. Diretrizes finais para o agente

- **Não confie no cliente:** toda validação e autorização no servidor.
- **Tudo filtrado por tenant e escopo de setor**, sempre.
- **Regras de negócio em `services/`**, cobertas por testes (pytest).
- **Movimentações e auditoria são append-only**; correções = novos registros.
- **Transações atômicas** em qualquer operação que toque saldo/ativo/documento.
- Prefira **simplicidade** (HTMX/Alpine) a frameworks JS pesados.
- Código, rotas, mensagens e documentação do usuário em **português do Brasil**;
  use nomes de variáveis claros e consistentes com o domínio.
- Entregue **migrações, seeds idempotentes, testes e README** junto com o código.
```
