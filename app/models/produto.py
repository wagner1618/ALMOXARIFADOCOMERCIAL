"""Produto — definição de catálogo (consumível ou durável)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.categoria import Categoria

# Tipos de controle (decisão central de modelagem).
TIPO_CONSUMIVEL = "CONSUMIVEL"
TIPO_DURAVEL = "DURAVEL"
TIPOS_CONTROLE = (TIPO_CONSUMIVEL, TIPO_DURAVEL)

ROTULO_TIPO = {
    TIPO_CONSUMIVEL: "Consumível (por quantidade)",
    TIPO_DURAVEL: "Durável / Patrimônio (serializado)",
}

UNIDADES_PADRAO = ("UN", "CX", "PC", "L", "ML", "KG", "G", "M", "CM", "PAR", "RESMA", "ROLO")


class Produto(TenantMixin, TimestampMixin, db.Model):
    """Definição de um material. NÃO representa a quantidade física."""

    __tablename__ = "produtos"
    __table_args__ = (UniqueConstraint("organizacao_id", "sku", name="uq_produto_org_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="SET NULL"), nullable=True, index=True
    )

    tipo_controle: Mapped[str] = mapped_column(String(12), nullable=False, default=TIPO_CONSUMIVEL)
    unidade: Mapped[str] = mapped_column(String(12), nullable=False, default="UN")

    estoque_minimo: Mapped[float] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    estoque_maximo: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)

    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)

    valor_unitario_referencia: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    custo_medio: Mapped[float] = mapped_column(Numeric(14, 4), default=0, nullable=False)

    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    foto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Valores dos campos customizados (chave -> valor).
    campos: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    categoria: Mapped[Categoria | None] = relationship()

    @property
    def is_consumivel(self) -> bool:
        return self.tipo_controle == TIPO_CONSUMIVEL

    @property
    def is_duravel(self) -> bool:
        return self.tipo_controle == TIPO_DURAVEL

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_TIPO.get(self.tipo_controle, self.tipo_controle)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Produto {self.sku} {self.nome!r}>"
