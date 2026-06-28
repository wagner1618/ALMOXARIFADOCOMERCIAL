"""SaldoEstoque — quantidade de um produto consumível em um setor."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.produto import Produto
    from app.models.setor import Setor


class SaldoEstoque(TenantMixin, TimestampMixin, db.Model):
    """Saldo de um produto em um setor. Nunca editado direto — só por movimentação.

    ``disponivel = quantidade - quantidade_em_transito``.
    """

    __tablename__ = "saldos_estoque"
    __table_args__ = (UniqueConstraint("produto_id", "setor_id", name="uq_saldo_produto_setor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(
        ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    setor_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantidade_em_transito: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), default=0, nullable=False
    )

    produto: Mapped[Produto] = relationship()
    setor: Mapped[Setor] = relationship()

    @property
    def disponivel(self) -> Decimal:
        return (self.quantidade or Decimal(0)) - (self.quantidade_em_transito or Decimal(0))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SaldoEstoque p={self.produto_id} s={self.setor_id} q={self.quantidade}>"
