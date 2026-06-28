"""Ativo — unidade patrimonial (durável serializado), com ciclo de vida."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.produto import Produto
    from app.models.setor import Setor
    from app.models.usuario import Usuario

# Estado de conservação.
BOM = "BOM"
REGULAR = "REGULAR"
DEFASADO = "DEFASADO"
INSERVIVEL = "INSERVIVEL"
ESTADOS_CONSERVACAO = (BOM, REGULAR, DEFASADO, INSERVIVEL)
ROTULO_ESTADO = {
    BOM: "Bom",
    REGULAR: "Regular",
    DEFASADO: "Defasado",
    INSERVIVEL: "Inservível",
}

# Status do ciclo de vida.
EM_ESTOQUE = "EM_ESTOQUE"
EM_USO = "EM_USO"
EMPRESTADO = "EMPRESTADO"
EM_MANUTENCAO = "EM_MANUTENCAO"
EM_TRANSITO = "EM_TRANSITO"
BAIXADO = "BAIXADO"
STATUS_CICLO = (EM_ESTOQUE, EM_USO, EMPRESTADO, EM_MANUTENCAO, EM_TRANSITO, BAIXADO)
ROTULO_STATUS = {
    EM_ESTOQUE: "Em estoque",
    EM_USO: "Em uso",
    EMPRESTADO: "Emprestado",
    EM_MANUTENCAO: "Em manutenção",
    EM_TRANSITO: "Em trânsito",
    BAIXADO: "Baixado",
}
COR_STATUS = {
    EM_ESTOQUE: "success",
    EM_USO: "primary",
    EMPRESTADO: "info",
    EM_MANUTENCAO: "warning",
    EM_TRANSITO: "secondary",
    BAIXADO: "dark",
}


class Ativo(TenantMixin, TimestampMixin, db.Model):
    """Exemplar físico único de um bem durável."""

    __tablename__ = "ativos"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "tombamento", name="uq_ativo_org_tombamento"),
        UniqueConstraint("organizacao_id", "numero_serie", name="uq_ativo_org_serie"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    tombamento: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    numero_serie: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fornecedor: Mapped[str | None] = mapped_column(String(160), nullable=True)

    data_aquisicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_aquisicao: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    garantia_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    vida_util_meses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valor_residual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    estado_conservacao: Mapped[str] = mapped_column(String(12), default=BOM, nullable=False)
    status_ciclo: Mapped[str] = mapped_column(
        String(14), default=EM_ESTOQUE, nullable=False, index=True
    )

    setor_atual_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usuario_responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    ultima_revisao_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    proxima_revisao_em: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    foto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    campos: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    produto: Mapped[Produto | None] = relationship()
    setor_atual: Mapped[Setor | None] = relationship()
    responsavel: Mapped[Usuario | None] = relationship()

    # ----- Propriedades de apoio ----------------------------------------- #
    @property
    def rotulo_status(self) -> str:
        return ROTULO_STATUS.get(self.status_ciclo, self.status_ciclo)

    @property
    def cor_status(self) -> str:
        return COR_STATUS.get(self.status_ciclo, "secondary")

    @property
    def rotulo_estado(self) -> str:
        return ROTULO_ESTADO.get(self.estado_conservacao, self.estado_conservacao)

    @property
    def is_inservivel(self) -> bool:
        return self.estado_conservacao == INSERVIVEL

    @property
    def revisao_vencida(self) -> bool:
        return self.proxima_revisao_em is not None and self.proxima_revisao_em < date.today()

    @property
    def valor_contabil(self) -> Decimal | None:
        """Depreciação linear simples até o valor residual (opcional)."""
        if self.valor_aquisicao is None or not self.vida_util_meses:
            return self.valor_aquisicao
        base = Decimal(self.valor_aquisicao)
        residual = Decimal(self.valor_residual or 0)
        inicio = self.data_aquisicao or self.criado_em.date()
        hoje = date.today()
        meses = (hoje.year - inicio.year) * 12 + (hoje.month - inicio.month)
        meses = max(0, min(meses, self.vida_util_meses))
        depreciacao = (base - residual) * Decimal(meses) / Decimal(self.vida_util_meses)
        return (base - depreciacao).quantize(Decimal("0.01"))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ativo {self.tombamento or self.id} {self.nome!r} {self.status_ciclo}>"
