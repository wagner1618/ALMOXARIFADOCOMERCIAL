"""RegraVisibilidade — visualização cruzada de estoque entre setores (§8.3).

Por padrão cada setor enxerga apenas o próprio estoque e o de sua subárvore.
Uma regra concede ao ``setor_observador`` acesso **somente leitura** ao estoque
do ``setor_alvo`` (e, opcionalmente, à subárvore do alvo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.setor import Setor


class RegraVisibilidade(TenantMixin, TimestampMixin, db.Model):
    """Concede a um setor a visualização (leitura) do estoque de outro."""

    __tablename__ = "regras_visibilidade"
    __table_args__ = (
        UniqueConstraint("setor_observador_id", "setor_alvo_id", name="uq_visibilidade_par"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setor_observador_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    setor_alvo_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Se True, a regra alcança também a subárvore do setor alvo.
    inclui_subarvore: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    observador: Mapped[Setor] = relationship(foreign_keys=[setor_observador_id])
    alvo: Mapped[Setor] = relationship(foreign_keys=[setor_alvo_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RegraVisibilidade {self.setor_observador_id}->{self.setor_alvo_id}>"
