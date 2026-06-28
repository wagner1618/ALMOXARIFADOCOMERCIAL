"""Setor — nó da hierarquia interna da organização (árvore)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.organizacao import Organizacao


class Setor(TenantMixin, TimestampMixin, db.Model):
    """Unidade organizacional. Modelada como árvore via ``setor_pai_id``.

    Suporta N níveis (principal → secundário → terciário → ...). O ``path``
    materializado (ex.: ``1/4/9``) permite consultas de subárvore rápidas.
    """

    __tablename__ = "setores"
    __table_args__ = (UniqueConstraint("organizacao_id", "codigo", name="uq_setor_org_codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(40), nullable=True)

    setor_pai_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Caminho materializado dos ancestrais inclusive o próprio id: "1/4/9".
    path: Mapped[str] = mapped_column(String(255), default="", nullable=False, index=True)
    nivel: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Visibilidade cruzada (ver §8.3)
    permite_visualizacao_externa: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Compras (§7.9)
    poder_compra: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    centro_custo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    orcamento_anual: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    organizacao: Mapped[Organizacao] = relationship(back_populates="setores")
    pai: Mapped[Setor | None] = relationship(remote_side="Setor.id", back_populates="filhos")
    filhos: Mapped[list[Setor]] = relationship(back_populates="pai", cascade="all, delete-orphan")

    @property
    def is_raiz(self) -> bool:
        return self.setor_pai_id is None

    def atualizar_path(self) -> None:
        """Recalcula ``path`` e ``nivel`` a partir do pai. Chamar após definir o id."""
        if self.pai is None:
            self.path = str(self.id)
            self.nivel = 1
        else:
            self.path = f"{self.pai.path}/{self.id}"
            self.nivel = self.pai.nivel + 1

    @property
    def ids_subarvore_prefix(self) -> str:
        """Prefixo para filtrar a subárvore: ``Setor.path.like(prefix + '%')``."""
        return f"{self.path}/"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setor {self.nome!r} path={self.path!r}>"
