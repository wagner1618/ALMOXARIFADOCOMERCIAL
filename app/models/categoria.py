"""Categoria — classificação de produtos/ativos, por organização."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin


class Categoria(TenantMixin, TimestampMixin, db.Model):
    """Agrupa produtos/ativos (ex.: Informática, Limpeza, Mobiliário)."""

    __tablename__ = "categorias"
    __table_args__ = (UniqueConstraint("organizacao_id", "nome", name="uq_categoria_org_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Categoria {self.nome!r}>"
