"""DefinicaoCampo — descreve um campo customizado de uma entidade (§6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.categoria import Categoria

# Entidades que aceitam campos customizados.
ENTIDADE_PRODUTO = "PRODUTO"
ENTIDADE_ATIVO = "ATIVO"
ENTIDADE_SETOR = "SETOR"
ENTIDADE_MOVIMENTACAO = "MOVIMENTACAO"
ENTIDADES = (ENTIDADE_PRODUTO, ENTIDADE_ATIVO, ENTIDADE_SETOR, ENTIDADE_MOVIMENTACAO)

# Tipos de campo suportados.
TIPO_TEXTO = "TEXTO"
TIPO_NUMERO = "NUMERO"
TIPO_DATA = "DATA"
TIPO_BOOLEANO = "BOOLEANO"
TIPO_SELECT = "SELECT"
TIPO_MULTISELECT = "MULTISELECT"
TIPO_ARQUIVO = "ARQUIVO"
TIPOS_CAMPO = (
    TIPO_TEXTO,
    TIPO_NUMERO,
    TIPO_DATA,
    TIPO_BOOLEANO,
    TIPO_SELECT,
    TIPO_MULTISELECT,
    TIPO_ARQUIVO,
)
TIPOS_COM_OPCOES = (TIPO_SELECT, TIPO_MULTISELECT)

ROTULO_TIPO_CAMPO = {
    TIPO_TEXTO: "Texto",
    TIPO_NUMERO: "Número",
    TIPO_DATA: "Data",
    TIPO_BOOLEANO: "Sim/Não",
    TIPO_SELECT: "Seleção única",
    TIPO_MULTISELECT: "Seleção múltipla",
    TIPO_ARQUIVO: "Arquivo/anexo",
}

ROTULO_ENTIDADE = {
    ENTIDADE_PRODUTO: "Produto",
    ENTIDADE_ATIVO: "Ativo",
    ENTIDADE_SETOR: "Setor",
    ENTIDADE_MOVIMENTACAO: "Movimentação",
}


class DefinicaoCampo(TenantMixin, TimestampMixin, db.Model):
    """Metadado de um campo customizado definido pelo cliente."""

    __tablename__ = "definicoes_campo"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "entidade", "chave", name="uq_def_campo_org_ent_chave"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entidade: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    chave: Mapped[str] = mapped_column(String(50), nullable=False)
    rotulo: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default=TIPO_TEXTO)

    # Lista de opções (para SELECT/MULTISELECT).
    opcoes: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ajuda: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Se definido, o campo só se aplica a produtos/ativos daquela categoria.
    aplica_a_categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias.id", ondelete="CASCADE"), nullable=True, index=True
    )

    categoria: Mapped[Categoria | None] = relationship()

    @property
    def tem_opcoes(self) -> bool:
        return self.tipo in TIPOS_COM_OPCOES

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_TIPO_CAMPO.get(self.tipo, self.tipo)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DefinicaoCampo {self.entidade}.{self.chave} ({self.tipo})>"
