"""Modelos SQLAlchemy. Importar tudo aqui garante registro no metadata."""

from __future__ import annotations

from app.models.ativo import Ativo
from app.models.auditoria import Auditoria
from app.models.categoria import Categoria
from app.models.compras import (
    NotaFiscal,
    NotaFiscalItem,
    PedidoCompra,
    PedidoCompraItem,
)
from app.models.definicao_campo import DefinicaoCampo
from app.models.estoque import SaldoEstoque
from app.models.fornecedor import Fornecedor
from app.models.localizacao import Localizacao
from app.models.movimentacao import LoteMovimentacao, Movimentacao
from app.models.organizacao import Organizacao
from app.models.produto import Produto
from app.models.publico import (
    AtaItem,
    AtaRegistroPrecos,
    Contrato,
    ContratoItem,
    DotacaoOrcamentaria,
    Empenho,
    Liquidacao,
    Pagamento,
    ProcessoContratacao,
    Recebimento,
    TermoAditivo,
)
from app.models.rbac import Papel, Permissao, UsuarioPapel, papel_permissao
from app.models.setor import Setor
from app.models.transferencia import Transferencia, TransferenciaItem
from app.models.usuario import Usuario
from app.models.visibilidade import RegraVisibilidade

__all__ = [
    "AtaItem",
    "AtaRegistroPrecos",
    "Ativo",
    "Auditoria",
    "Categoria",
    "Contrato",
    "ContratoItem",
    "DefinicaoCampo",
    "DotacaoOrcamentaria",
    "Empenho",
    "Fornecedor",
    "Liquidacao",
    "Localizacao",
    "LoteMovimentacao",
    "Movimentacao",
    "NotaFiscal",
    "NotaFiscalItem",
    "Organizacao",
    "Pagamento",
    "Papel",
    "PedidoCompra",
    "PedidoCompraItem",
    "Permissao",
    "ProcessoContratacao",
    "Produto",
    "Recebimento",
    "RegraVisibilidade",
    "SaldoEstoque",
    "Setor",
    "TermoAditivo",
    "Transferencia",
    "TransferenciaItem",
    "Usuario",
    "UsuarioPapel",
    "papel_permissao",
]
