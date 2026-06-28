"""Mixins e tipos reutilizáveis pelos modelos."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

# JSON portável: usa JSONB no PostgreSQL, JSON genérico no SQLite (dev/testes).
JSONType = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    """Adiciona ``criado_em`` e ``atualizado_em`` automáticos."""

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """Adiciona ``organizacao_id`` — a coluna de isolamento multi-tenant.

    Toda entidade pertencente a uma organização herda este mixin. As consultas
    devem SEMPRE filtrar por ``organizacao_id`` (ver app/security/tenant.py).
    """

    organizacao_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizacoes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
