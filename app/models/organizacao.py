"""Organização — o tenant, raiz do isolamento de dados."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TimestampMixin

if TYPE_CHECKING:
    from app.models.setor import Setor
    from app.models.usuario import Usuario


class Organizacao(TimestampMixin, db.Model):
    """Cliente que comprou o sistema. Raiz de todo o isolamento multi-tenant."""

    __tablename__ = "organizacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    cnpj: Mapped[str | None] = mapped_column(String(20), nullable=True)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plano: Mapped[str] = mapped_column(String(40), default="basico", nullable=False)

    # White-label
    logo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cor_primaria: Mapped[str] = mapped_column(String(9), default="#0d6efd", nullable=False)
    cor_secundaria: Mapped[str] = mapped_column(String(9), default="#6c757d", nullable=False)

    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Preferências, flags de visibilidade, modo_compra (PRIVADO|PUBLICO), etc.
    config: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    # Relacionamentos
    usuarios: Mapped[list[Usuario]] = relationship(
        back_populates="organizacao", cascade="all, delete-orphan"
    )
    setores: Mapped[list[Setor]] = relationship(
        back_populates="organizacao", cascade="all, delete-orphan"
    )

    @property
    def modo_compra(self) -> str:
        return self.config.get("modo_compra", "PRIVADO")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Organizacao {self.slug!r}>"
