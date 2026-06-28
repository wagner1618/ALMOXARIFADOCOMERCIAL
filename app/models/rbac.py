"""RBAC — Papéis, Permissões e o vínculo Usuário↔Papel↔Setor (escopo)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.setor import Setor
    from app.models.usuario import Usuario


# Associação Papel <-> Permissao (muitos-para-muitos)
papel_permissao = Table(
    "papel_permissao",
    db.metadata,
    Column("papel_id", ForeignKey("papeis.id", ondelete="CASCADE"), primary_key=True),
    Column("permissao_id", ForeignKey("permissoes.id", ondelete="CASCADE"), primary_key=True),
)


class Permissao(db.Model):
    """Catálogo global de permissões granulares (ex.: ``movimentacao.saida``).

    Não é tenant-scoped: é semeado a partir do registro em
    ``app/security/permissions.py`` e referenciado pelos papéis de cada org.
    """

    __tablename__ = "permissoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chave: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False, default="geral")
    descricao: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Permissao {self.chave!r}>"


class Papel(TenantMixin, TimestampMixin, db.Model):
    """Conjunto de permissões com um nível hierárquico, por organização."""

    __tablename__ = "papeis"
    __table_args__ = (UniqueConstraint("organizacao_id", "nome", name="uq_papel_org_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(60), nullable=False)
    nivel: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Papel de sistema (semente) não pode ser excluído pelo cliente.
    sistema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    permissoes: Mapped[list[Permissao]] = relationship(secondary=papel_permissao, lazy="selectin")
    atribuicoes: Mapped[list[UsuarioPapel]] = relationship(
        back_populates="papel", cascade="all, delete-orphan"
    )

    @property
    def chaves_permissao(self) -> set[str]:
        return {p.chave for p in self.permissoes}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Papel {self.nome!r} nivel={self.nivel}>"


class UsuarioPapel(TimestampMixin, db.Model):
    """Vincula um usuário a um papel COM escopo de setor.

    ``setor_id`` nulo = escopo de organização inteira. Caso contrário, o papel
    vale para o setor e toda a sua subárvore (via ``path`` materializado).
    """

    __tablename__ = "usuario_papel"
    __table_args__ = (
        UniqueConstraint("usuario_id", "papel_id", "setor_id", name="uq_usuario_papel_setor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    papel_id: Mapped[int] = mapped_column(
        ForeignKey("papeis.id", ondelete="CASCADE"), nullable=False
    )
    setor_id: Mapped[int | None] = mapped_column(
        ForeignKey("setores.id", ondelete="CASCADE"), nullable=True
    )

    usuario: Mapped[Usuario] = relationship(back_populates="papeis")
    papel: Mapped[Papel] = relationship(back_populates="atribuicoes")
    setor: Mapped[Setor | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UsuarioPapel u={self.usuario_id} p={self.papel_id} setor={self.setor_id}>"
