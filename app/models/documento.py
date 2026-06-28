"""Documentos (§7.7) — comprovantes emitidos e armazenados, e seus modelos editáveis.

Um ``Documento`` é gerado a partir de um ``ModeloDocumento`` (HTML/Jinja editável
pela organização), recebe **numeração sequencial** por organização/tipo/ano, guarda
o **hash** do arquivo (integridade) e um **snapshot JSONB** dos dados no momento da
emissão. O PDF é renderizado pelo WeasyPrint quando disponível; caso contrário, o
documento é armazenado como HTML imprimível (o subsistema funciona em ambos os casos).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import JSONType, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.setor import Setor
    from app.models.usuario import Usuario


# Tipos de documento (espelham as operações que podem gerar comprovante).
SAIDA = "SAIDA"
RECEBIMENTO = "RECEBIMENTO"
DEVOLUCAO = "DEVOLUCAO"
TRANSFERENCIA = "TRANSFERENCIA"
BAIXA = "BAIXA"
TERMO_RESPONSABILIDADE = "TERMO_RESPONSABILIDADE"
INVENTARIO = "INVENTARIO"
TIPOS_DOCUMENTO = (
    SAIDA, RECEBIMENTO, DEVOLUCAO, TRANSFERENCIA, BAIXA, TERMO_RESPONSABILIDADE, INVENTARIO,
)
ROTULO_DOCUMENTO = {
    SAIDA: "Saída",
    RECEBIMENTO: "Recebimento",
    DEVOLUCAO: "Devolução",
    TRANSFERENCIA: "Transferência",
    BAIXA: "Baixa",
    TERMO_RESPONSABILIDADE: "Termo de responsabilidade",
    INVENTARIO: "Inventário",
}


class ModeloDocumento(TenantMixin, TimestampMixin, db.Model):
    """Template HTML/Jinja editável por organização, um por tipo de documento."""

    __tablename__ = "modelos_documento"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "tipo", name="uq_modelo_org_tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    conteudo_html: Mapped[str] = mapped_column(Text, nullable=False)
    ativo: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_DOCUMENTO.get(self.tipo, self.tipo)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModeloDocumento {self.tipo} {self.nome!r}>"


class Documento(TenantMixin, TimestampMixin, db.Model):
    """Comprovante emitido: arquivo + numeração + hash + snapshot dos dados."""

    __tablename__ = "documentos"
    __table_args__ = (
        UniqueConstraint(
            "organizacao_id", "tipo", "ano", "sequencial", name="uq_documento_numero"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    sequencial: Mapped[int] = mapped_column(Integer, nullable=False)
    ano: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    numero: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)

    setor_origem_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    setor_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="SET NULL"), nullable=True, index=True
    )
    modelo_id: Mapped[int | None] = mapped_column(
        ForeignKey("modelos_documento.id", ondelete="SET NULL"), nullable=True
    )
    emitido_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    formato: Mapped[str] = mapped_column(String(8), default="pdf", nullable=False)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assinado_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dados: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)

    setor_origem: Mapped[Setor | None] = relationship(foreign_keys=[setor_origem_id])
    setor_destino: Mapped[Setor | None] = relationship(foreign_keys=[setor_destino_id])
    modelo: Mapped[ModeloDocumento | None] = relationship()
    emitido_por: Mapped[Usuario | None] = relationship()

    @property
    def rotulo_tipo(self) -> str:
        return ROTULO_DOCUMENTO.get(self.tipo, self.tipo)

    @property
    def is_pdf(self) -> bool:
        return self.formato == "pdf"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Documento {self.numero}>"
