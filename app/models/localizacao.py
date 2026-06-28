"""Localizacao — local físico (prateleira/sala) dentro de um setor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.setor import Setor


class Localizacao(TenantMixin, TimestampMixin, db.Model):
    """Posição física dentro de um setor (ex.: Prateleira A3, Sala 12)."""

    __tablename__ = "localizacoes"
    __table_args__ = (UniqueConstraint("setor_id", "nome", name="uq_localizacao_setor_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setor_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    setor: Mapped[Setor] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Localizacao {self.nome!r} setor={self.setor_id}>"
