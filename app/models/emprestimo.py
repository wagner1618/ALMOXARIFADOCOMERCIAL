"""Empréstimos (§7.5) — cessão temporária de consumível (por quantidade) ou
durável (exemplar único), com devolução total/parcial e controle de vencidos.

Regras mantidas pelo ``emprestimo_service``:
- Consumível: empréstimo subtrai saldo; devolução (total ou parcial) repõe saldo.
- Durável: empréstimo muda ``status_ciclo`` do ativo para EMPRESTADO; devolução é
  sempre integral e devolve o ativo ao estoque.
- ``status`` persistido é ATIVO | PARCIAL | DEVOLVIDO; **vencido** é derivado da
  data prevista (não precisa de job) e exibido como rótulo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.ativo import Ativo
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario


ATIVO = "ATIVO"
PARCIAL = "PARCIAL"
DEVOLVIDO = "DEVOLVIDO"
STATUS_EMPRESTIMO = (ATIVO, PARCIAL, DEVOLVIDO)
EM_ABERTO = (ATIVO, PARCIAL)  # ainda pendentes de devolução

ROTULO_STATUS = {ATIVO: "Ativo", PARCIAL: "Parcial", DEVOLVIDO: "Devolvido"}
COR_STATUS = {ATIVO: "primary", PARCIAL: "info", DEVOLVIDO: "success"}


class Emprestimo(TenantMixin, TimestampMixin, db.Model):
    """Cessão temporária de um item a um setor/destinatário."""

    __tablename__ = "emprestimos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ativo_id: Mapped[int | None] = mapped_column(
        ForeignKey("ativos.id", ondelete="SET NULL"), nullable=True, index=True
    )

    quantidade: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=1, nullable=False)
    quantidade_devolvida: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)

    setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destinatario: Mapped[str | None] = mapped_column(String(160), nullable=True)
    responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    data_emprestimo: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_prevista: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    data_devolucao: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(12), default=ATIVO, nullable=False, index=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    produto: Mapped[Produto | None] = relationship()
    ativo: Mapped[Ativo | None] = relationship()
    setor: Mapped[Setor | None] = relationship()
    responsavel: Mapped[Usuario | None] = relationship()

    # ----- Propriedades de apoio ----------------------------------------- #
    @property
    def is_duravel(self) -> bool:
        return self.ativo_id is not None

    @property
    def quantidade_pendente(self) -> Decimal:
        return Decimal(self.quantidade or 0) - Decimal(self.quantidade_devolvida or 0)

    @property
    def em_aberto(self) -> bool:
        return self.status in EM_ABERTO

    @property
    def vencido(self) -> bool:
        return (
            self.em_aberto
            and self.data_prevista is not None
            and self.data_prevista < date.today()
        )

    @property
    def descricao_item(self) -> str:
        if self.ativo is not None:
            return self.ativo.nome
        if self.produto is not None:
            return self.produto.nome
        return "—"

    @property
    def rotulo_status(self) -> str:
        if self.vencido:
            return "Vencido"
        return ROTULO_STATUS.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        if self.vencido:
            return "danger"
        return COR_STATUS.get(self.status, "secondary")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Emprestimo {self.id} {self.status} item={self.descricao_item!r}>"
