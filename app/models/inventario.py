"""Inventário (§7.4/§8) — recontagem de consumíveis e recertificação de ativos.

Um ``Inventario`` cobre um setor e um tipo (CONSUMIVEL ou ATIVO). Ao abrir, faz um
**snapshot** do que se espera encontrar (saldo de cada produto, ou estado/situação de
cada ativo). A contagem preenche o encontrado; ao fechar:
- Consumível: cada divergência vira um ``AJUSTE_INVENTARIO`` (corrige o saldo).
- Ativo: confirma ``estado_conservacao``/``status_ciclo`` e renova as datas de revisão.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.ativo import Ativo
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario


INV_CONSUMIVEL = "CONSUMIVEL"
INV_ATIVO = "ATIVO"
TIPOS_INVENTARIO = (INV_CONSUMIVEL, INV_ATIVO)
ROTULO_TIPO = {INV_CONSUMIVEL: "Consumíveis", INV_ATIVO: "Ativos (recertificação)"}

ABERTO = "ABERTO"
FECHADO = "FECHADO"
CANCELADO = "CANCELADO"
STATUS_INVENTARIO = (ABERTO, FECHADO, CANCELADO)
ROTULO_STATUS = {ABERTO: "Em contagem", FECHADO: "Fechado", CANCELADO: "Cancelado"}
COR_STATUS = {ABERTO: "primary", FECHADO: "success", CANCELADO: "secondary"}


class Inventario(TenantMixin, TimestampMixin, db.Model):
    """Ciclo de recontagem/recertificação de um setor."""

    __tablename__ = "inventarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(12), default=ABERTO, nullable=False, index=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fechamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    setor: Mapped[Setor | None] = relationship()
    responsavel: Mapped[Usuario | None] = relationship()
    itens: Mapped[list[InventarioItem]] = relationship(
        back_populates="inventario", cascade="all, delete-orphan"
    )

    @property
    def is_consumivel(self) -> bool:
        return self.tipo == INV_CONSUMIVEL

    @property
    def aberto(self) -> bool:
        return self.status == ABERTO

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_TIPO.get(self.tipo, self.tipo)

    @property
    def rotulo_status(self) -> str:
        return ROTULO_STATUS.get(self.status, self.status)

    @property
    def cor_status(self) -> str:
        return COR_STATUS.get(self.status, "secondary")

    @property
    def total_itens(self) -> int:
        return len(self.itens)

    @property
    def itens_contados(self) -> int:
        return sum(1 for i in self.itens if i.contado)

    @property
    def itens_divergentes(self) -> int:
        return sum(1 for i in self.itens if i.divergencia)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Inventario #{self.numero} {self.tipo} {self.status}>"


class InventarioItem(TenantMixin, TimestampMixin, db.Model):
    """Linha do inventário: um produto (esperado vs contado) ou um ativo (recertificação)."""

    __tablename__ = "inventario_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventario_id: Mapped[int] = mapped_column(
        ForeignKey("inventarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ativo_id: Mapped[int | None] = mapped_column(
        ForeignKey("ativos.id", ondelete="SET NULL"), nullable=True, index=True
    )

    quantidade_esperada: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantidade_contada: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    estado_conservacao: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status_ciclo: Mapped[str | None] = mapped_column(String(14), nullable=True)

    contado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    divergencia: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    inventario: Mapped[Inventario] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()
    ativo: Mapped[Ativo | None] = relationship()

    @property
    def descricao(self) -> str:
        if self.ativo is not None:
            return f"{self.ativo.tombamento or self.ativo.id} · {self.ativo.nome}"
        if self.produto is not None:
            return f"{self.produto.sku} · {self.produto.nome}"
        return "—"

    @property
    def diferenca(self) -> Decimal:
        if self.quantidade_contada is None:
            return Decimal(0)
        return Decimal(self.quantidade_contada) - Decimal(self.quantidade_esperada or 0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InventarioItem {self.descricao!r} contado={self.contado}>"
