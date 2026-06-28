"""Transferencia e TransferenciaItem — fluxo de envio com confirmação (§7.8)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.produto import Produto
    from app.models.setor import Setor

# Estados da máquina de transferência.
RASCUNHO = "RASCUNHO"
ENVIADA = "ENVIADA"
RECEBIDA = "RECEBIDA"
RECEBIDA_COM_DIVERGENCIA = "RECEBIDA_COM_DIVERGENCIA"
CORRIGIDA = "CORRIGIDA"
CANCELADA = "CANCELADA"

STATUS_TRANSFERENCIA = (
    RASCUNHO,
    ENVIADA,
    RECEBIDA,
    RECEBIDA_COM_DIVERGENCIA,
    CORRIGIDA,
    CANCELADA,
)

ROTULO_STATUS = {
    RASCUNHO: "Rascunho",
    ENVIADA: "Enviada (em trânsito)",
    RECEBIDA: "Recebida",
    RECEBIDA_COM_DIVERGENCIA: "Recebida com divergência",
    CORRIGIDA: "Corrigida",
    CANCELADA: "Cancelada",
}

COR_STATUS = {
    RASCUNHO: "secondary",
    ENVIADA: "info",
    RECEBIDA: "success",
    RECEBIDA_COM_DIVERGENCIA: "warning",
    CORRIGIDA: "primary",
    CANCELADA: "dark",
}


class Transferencia(TenantMixin, TimestampMixin, db.Model):
    """Cabeçalho de uma transferência entre setores (envio com confirmação)."""

    __tablename__ = "transferencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    setor_origem_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    setor_destino_id: Mapped[int] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(28), default=ENVIADA, nullable=False, index=True)

    enviado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recebido_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    recebido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    corrigido_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    corrigido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    observacoes_envio: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacoes_recebimento: Mapped[str | None] = mapped_column(Text, nullable=True)
    observacoes_correcao: Mapped[str | None] = mapped_column(Text, nullable=True)

    documento_envio_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    documento_recebimento_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    origem: Mapped[Setor] = relationship(foreign_keys=[setor_origem_id])
    destino: Mapped[Setor] = relationship(foreign_keys=[setor_destino_id])
    itens: Mapped[list[TransferenciaItem]] = relationship(
        back_populates="transferencia", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def rotulo_status(self) -> str:
        return ROTULO_STATUS.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_STATUS.get(self.status, "secondary")

    @property
    def tem_divergencia(self) -> bool:
        return any(i.divergencia for i in self.itens)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transferencia #{self.numero} {self.status}>"


class TransferenciaItem(db.Model):
    """Linha conferida de uma transferência (por enquanto, só consumíveis)."""

    __tablename__ = "transferencia_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transferencia_id: Mapped[int] = mapped_column(
        ForeignKey("transferencias.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ativo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    quantidade_enviada: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantidade_recebida: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantidade_corrigida: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    divergencia: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    motivo_divergencia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    transferencia: Mapped[Transferencia] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()

    @property
    def pendente_transito(self) -> Decimal:
        """Quantidade ainda reservada em trânsito (não recebida nem corrigida)."""
        recebida = self.quantidade_recebida if self.quantidade_recebida is not None else Decimal(0)
        corrigida = (
            self.quantidade_corrigida if self.quantidade_corrigida is not None else Decimal(0)
        )
        return Decimal(self.quantidade_enviada) - Decimal(recebida) - Decimal(corrigida)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TransferenciaItem t={self.transferencia_id} p={self.produto_id}>"
