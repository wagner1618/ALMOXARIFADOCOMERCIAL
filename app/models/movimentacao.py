"""Movimentacao (trilha append-only) e LoteMovimentacao."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario

# Tipos de movimentação.
ENTRADA = "ENTRADA"
SAIDA = "SAIDA"
TRANSFERENCIA = "TRANSFERENCIA"
EMPRESTIMO = "EMPRESTIMO"
DEVOLUCAO = "DEVOLUCAO"
BAIXA = "BAIXA"
AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"
TIPOS_MOVIMENTACAO = (
    ENTRADA,
    SAIDA,
    TRANSFERENCIA,
    EMPRESTIMO,
    DEVOLUCAO,
    BAIXA,
    AJUSTE_INVENTARIO,
)

ROTULO_MOVIMENTACAO = {
    ENTRADA: "Entrada",
    SAIDA: "Saída",
    TRANSFERENCIA: "Transferência",
    EMPRESTIMO: "Empréstimo",
    DEVOLUCAO: "Devolução",
    BAIXA: "Baixa",
    AJUSTE_INVENTARIO: "Ajuste de inventário",
}


class LoteMovimentacao(TenantMixin, TimestampMixin, db.Model):
    """Agrupa várias movimentações de uma única operação (lançamento em lote)."""

    __tablename__ = "lotes_movimentacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    movimentacoes: Mapped[list[Movimentacao]] = relationship(back_populates="lote")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LoteMovimentacao #{self.numero}>"


class Movimentacao(TenantMixin, TimestampMixin, db.Model):
    """Evento imutável que altera saldo ou localização. NUNCA é editado/excluído."""

    __tablename__ = "movimentacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # FK para ``ativos`` será adicionada na Fase 5 (a tabela ainda não existe).
    ativo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    origem_setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destino_setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )

    valor_unitario: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    destinatario: Mapped[str | None] = mapped_column(String(160), nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    lote_id: Mapped[int | None] = mapped_column(
        ForeignKey("lotes_movimentacao.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # documento_id / nota_fiscal_id virão nas fases de documentos e compras.

    produto: Mapped[Produto | None] = relationship()
    usuario: Mapped[Usuario | None] = relationship()
    origem: Mapped[Setor | None] = relationship(foreign_keys=[origem_setor_id])
    destino: Mapped[Setor | None] = relationship(foreign_keys=[destino_setor_id])
    lote: Mapped[LoteMovimentacao | None] = relationship(back_populates="movimentacoes")

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_MOVIMENTACAO.get(self.tipo, self.tipo)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Movimentacao {self.tipo} q={self.quantidade} p={self.produto_id}>"
