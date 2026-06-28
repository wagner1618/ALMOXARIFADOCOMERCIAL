"""Catálogo de permissões e definição dos papéis padrão (sementes).

Fonte única de verdade: o ``seed`` lê estes dicionários para popular as tabelas
``permissoes`` e ``papeis``. Adicionar uma permissão aqui e rodar o seed basta.
"""

from __future__ import annotations

# chave -> (categoria, descrição)
PERMISSOES: dict[str, tuple[str, str]] = {
    # Estoque / catálogo
    "produto.ver": ("estoque", "Visualizar produtos e saldos"),
    "produto.criar": ("estoque", "Cadastrar/editar produtos"),
    "movimentacao.entrada": ("estoque", "Registrar entradas de estoque"),
    "movimentacao.saida": ("estoque", "Registrar saídas/distribuições"),
    "inventario.realizar": ("estoque", "Realizar inventário/recontagem"),
    # Ativos / patrimônio
    "ativo.ver": ("ativos", "Visualizar ativos/patrimônio"),
    "ativo.gerenciar": ("ativos", "Cadastrar/editar ativos"),
    "ativo.baixar": ("ativos", "Dar baixa em ativos"),
    # Transferências
    "transferencia.enviar": ("transferencia", "Enviar transferência (origem)"),
    "transferencia.receber": ("transferencia", "Receber/conferir transferência (destino)"),
    "transferencia.corrigir": ("transferencia", "Corrigir transferência divergente"),
    # Empréstimos
    "emprestimo.gerenciar": ("emprestimo", "Emprestar e registrar devoluções"),
    # Compras (setor com poder de compra)
    "compra.pedido": ("compras", "Criar pedidos de compra"),
    "compra.aprovar": ("compras", "Aprovar pedidos de compra"),
    "compra.nota_fiscal": ("compras", "Registrar notas fiscais"),
    "compra.entrada_valorada": ("compras", "Dar entrada valorada a partir da NF"),
    "fornecedor.gerenciar": ("compras", "Gerenciar fornecedores"),
    # Compras públicas (modo PÚBLICO)
    "licitacao.gerenciar": ("publico", "Gerenciar processos de contratação"),
    "ata.gerenciar": ("publico", "Gerenciar atas de registro de preços"),
    "contrato.gerenciar": ("publico", "Gerenciar contratos e aditivos"),
    "empenho.emitir": ("publico", "Emitir notas de empenho"),
    "recebimento.definitivo": ("publico", "Realizar recebimento definitivo"),
    "despesa.liquidar": ("publico", "Liquidar despesa"),
    "despesa.pagar": ("publico", "Registrar pagamento"),
    "dotacao.gerenciar": ("publico", "Gerenciar dotações orçamentárias"),
    # Documentos
    "documento.emitir": ("documentos", "Emitir/reimprimir documentos"),
    # Administração da organização
    "usuario.gerenciar": ("admin", "Gerenciar usuários"),
    "papel.gerenciar": ("admin", "Gerenciar papéis e permissões"),
    "setor.gerenciar": ("admin", "Gerenciar setores"),
    "config.campos": ("admin", "Configurar campos customizados"),
    "config.visibilidade": ("admin", "Configurar visibilidade entre setores"),
    "config.compras": ("admin", "Configurar parâmetros de compras"),
    "config.organizacao": ("admin", "Configurar a organização (white-label, etc.)"),
    "relatorio.ver": ("relatorios", "Acessar relatórios e métricas"),
}


def todas_as_chaves() -> list[str]:
    return list(PERMISSOES.keys())


def chaves_por_categoria(*categorias: str) -> set[str]:
    return {k for k, (cat, _) in PERMISSOES.items() if cat in categorias}


_ADMIN_ORG = set(PERMISSOES.keys())
_GESTOR = chaves_por_categoria(
    "estoque", "ativos", "transferencia", "emprestimo", "documentos", "relatorios"
)
_COMPRADOR = chaves_por_categoria("compras") | {"produto.ver", "relatorio.ver"}
_OPERADOR = {
    "produto.ver",
    "movimentacao.entrada",
    "movimentacao.saida",
    "ativo.ver",
    "transferencia.enviar",
    "transferencia.receber",
    "emprestimo.gerenciar",
    "documento.emitir",
}
_CONSULTA = {"produto.ver", "ativo.ver", "relatorio.ver"}


# nome -> (nivel, descrição, conjunto de permissões)
PAPEIS_PADRAO: dict[str, tuple[int, str, set[str]]] = {
    "Administrador da Organização": (
        90,
        "Controle total dentro da organização",
        _ADMIN_ORG,
    ),
    "Gestor de Setor": (
        60,
        "Gerencia seu setor e a subárvore: cadastra, movimenta, transfere, inventaria",
        _GESTOR,
    ),
    "Comprador / Financeiro": (
        50,
        "Pedidos, fornecedores, notas fiscais e entradas valoradas",
        _COMPRADOR,
    ),
    "Operador": (
        30,
        "Registra movimentações, empréstimos e recebimentos no seu escopo",
        _OPERADOR,
    ),
    "Consulta": (10, "Somente leitura", _CONSULTA),
}
