"""Auditoria — log append-only de ações sensíveis."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import JSONType, TimestampMixin


class Auditoria(TimestampMixin, db.Model):
    """Registro imutável de quem fez o quê, quando e de onde.

    Nunca é editado ou excluído — correções entram como novos registros.
    """

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organizacao_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    acao: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entidade: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    dados_antes: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    dados_depois: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Auditoria {self.acao!r} {self.entidade}:{self.entidade_id}>"
