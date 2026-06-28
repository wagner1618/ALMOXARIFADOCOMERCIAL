"""Fornecedor — cadastro de quem fornece materiais/serviços (§7.9)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import JSONType, TenantMixin, TimestampMixin

# Tipo de pessoa.
PESSOA_JURIDICA = "PJ"
PESSOA_FISICA = "PF"
TIPOS_PESSOA = (PESSOA_JURIDICA, PESSOA_FISICA)
ROTULO_PESSOA = {PESSOA_JURIDICA: "Pessoa jurídica (CNPJ)", PESSOA_FISICA: "Pessoa física (CPF)"}


class Fornecedor(TenantMixin, TimestampMixin, db.Model):
    """Fornecedor da organização. Documento (CNPJ/CPF) é único quando informado."""

    __tablename__ = "fornecedores"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "documento", name="uq_fornecedor_org_documento"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tipo_pessoa: Mapped[str] = mapped_column(String(2), default=PESSOA_JURIDICA, nullable=False)
    documento: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(30), nullable=True)

    contato: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(255), nullable=True)

    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)
    campos: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    @property
    def rotulo_pessoa(self) -> str:
        return ROTULO_PESSOA.get(self.tipo_pessoa, self.tipo_pessoa)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Fornecedor {self.nome!r} doc={self.documento!r}>"
