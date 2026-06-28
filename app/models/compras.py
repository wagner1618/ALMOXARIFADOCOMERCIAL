"""Compras (§7.9): PedidoCompra e NotaFiscal, com seus itens.

Fluxo privado/comum: o pedido (opcional) passa por aprovação por alçada e é
controlado contra o orçamento anual do setor; a nota fiscal recebe o anexo
(PDF/XML) e dispara a entrada valorada no estoque/patrimônio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.fornecedor import Fornecedor
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario

# ------------------------------------------------------------------ Pedido --- #
# Ciclo de vida do pedido de compra.
RASCUNHO = "RASCUNHO"
APROVADO = "APROVADO"
EMPENHADO = "EMPENHADO"
CONCLUIDO = "CONCLUIDO"
CANCELADO = "CANCELADO"
STATUS_PEDIDO = (RASCUNHO, APROVADO, EMPENHADO, CONCLUIDO, CANCELADO)
ROTULO_PEDIDO = {
    RASCUNHO: "Rascunho",
    APROVADO: "Aprovado",
    EMPENHADO: "Empenhado",
    CONCLUIDO: "Concluído",
    CANCELADO: "Cancelado",
}
COR_PEDIDO = {
    RASCUNHO: "secondary",
    APROVADO: "info",
    EMPENHADO: "primary",
    CONCLUIDO: "success",
    CANCELADO: "danger",
}
# Status que comprometem orçamento (consomem a dotação anual do setor).
STATUS_COMPROMETE_ORCAMENTO = (APROVADO, EMPENHADO, CONCLUIDO)


class PedidoCompra(TenantMixin, TimestampMixin, db.Model):
    """Requisição/pedido de compra de um setor com poder de compra."""

    __tablename__ = "pedidos_compra"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "numero", name="uq_pedido_org_numero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    exercicio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    setor_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("fornecedores.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(12), default=RASCUNHO, nullable=False, index=True)
    valor_estimado: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    solicitante_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    aprovador_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    data_aprovacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    setor: Mapped[Setor] = relationship()
    fornecedor: Mapped[Fornecedor | None] = relationship()
    solicitante: Mapped[Usuario | None] = relationship(foreign_keys=[solicitante_id])
    aprovador: Mapped[Usuario | None] = relationship(foreign_keys=[aprovador_id])
    itens: Mapped[list[PedidoCompraItem]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )

    @property
    def rotulo_status(self) -> str:
        return ROTULO_PEDIDO.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_PEDIDO.get(self.status, "secondary")

    @property
    def editavel(self) -> bool:
        return self.status == RASCUNHO

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PedidoCompra #{self.numero} {self.status}>"


class PedidoCompraItem(TenantMixin, TimestampMixin, db.Model):
    """Item de um pedido de compra (produto opcional + descrição livre)."""

    __tablename__ = "pedido_compra_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedidos_compra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=1, nullable=False)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    pedido: Mapped[PedidoCompra] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PedidoCompraItem {self.descricao!r} q={self.quantidade}>"


# ------------------------------------------------------------- Nota fiscal --- #
# Status de processamento da NF.
NF_REGISTRADA = "REGISTRADA"
NF_LANCADA = "LANCADA"
STATUS_NF = (NF_REGISTRADA, NF_LANCADA)
ROTULO_NF = {NF_REGISTRADA: "Registrada", NF_LANCADA: "Lançada (entrada valorada)"}
COR_NF = {NF_REGISTRADA: "warning", NF_LANCADA: "success"}


class NotaFiscal(TenantMixin, TimestampMixin, db.Model):
    """Nota fiscal de entrada, com anexo (PDF/XML) e itens valorados."""

    __tablename__ = "notas_fiscais"
    __table_args__ = (
        UniqueConstraint(
            "organizacao_id", "fornecedor_id", "numero", "serie", name="uq_nf_org_forn_num_serie"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    serie: Mapped[str | None] = mapped_column(String(10), nullable=True)
    chave_nfe: Mapped[str | None] = mapped_column(String(44), nullable=True, index=True)

    fornecedor_id: Mapped[int] = mapped_column(
        ForeignKey("fornecedores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    setor_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    pedido_id: Mapped[int | None] = mapped_column(
        ForeignKey("pedidos_compra.id", ondelete="SET NULL"), nullable=True, index=True
    )

    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_entrada: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    arquivo_pdf: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arquivo_xml: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(12), default=NF_REGISTRADA, nullable=False, index=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    fornecedor: Mapped[Fornecedor] = relationship()
    setor: Mapped[Setor] = relationship()
    pedido: Mapped[PedidoCompra | None] = relationship()
    usuario: Mapped[Usuario | None] = relationship()
    itens: Mapped[list[NotaFiscalItem]] = relationship(
        back_populates="nota", cascade="all, delete-orphan"
    )

    @property
    def rotulo_status(self) -> str:
        return ROTULO_NF.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_NF.get(self.status, "secondary")

    @property
    def lancada(self) -> bool:
        return self.status == NF_LANCADA

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotaFiscal {self.numero}/{self.serie} {self.status}>"


class NotaFiscalItem(TenantMixin, TimestampMixin, db.Model):
    """Item de uma nota fiscal — vincula um produto e seu valor de aquisição."""

    __tablename__ = "nota_fiscal_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nota_id: Mapped[int] = mapped_column(
        ForeignKey("notas_fiscais.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=1, nullable=False)
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    nota: Mapped[NotaFiscal] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotaFiscalItem {self.descricao!r} q={self.quantidade}>"
