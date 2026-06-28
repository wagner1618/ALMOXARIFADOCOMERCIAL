"""Usuário — autenticação (Argon2 + 2FA) e resolução de permissões."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.organizacao import Organizacao
    from app.models.rbac import UsuarioPapel

_hasher = PasswordHasher()


class Usuario(TenantMixin, TimestampMixin, UserMixin, db.Model):
    """Operador do sistema, pertencente a uma organização."""

    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "email", name="uq_usuario_org_email"),
        UniqueConstraint("organizacao_id", "username", name="uq_usuario_org_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    cargo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    matricula: Mapped[str | None] = mapped_column(String(40), nullable=True)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Operador da plataforma (acima do tenant) — gerencia organizações/licenças.
    superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Força troca de senha no próximo login (senha inicial / reset).
    deve_trocar_senha: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organizacao: Mapped[Organizacao] = relationship(back_populates="usuarios")
    papeis: Mapped[list[UsuarioPapel]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="selectin"
    )

    # ----- Senha (Argon2) -------------------------------------------------
    def definir_senha(self, senha: str) -> None:
        self.senha_hash = _hasher.hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        try:
            _hasher.verify(self.senha_hash, senha)
        except VerifyMismatchError:
            return False
        # Re-hash transparente se os parâmetros do Argon2 mudaram.
        if _hasher.check_needs_rehash(self.senha_hash):
            self.senha_hash = _hasher.hash(senha)
        return True

    # ----- 2FA ------------------------------------------------------------
    @property
    def tem_2fa(self) -> bool:
        return bool(self.totp_secret)

    # ----- Permissões -----------------------------------------------------
    @property
    def permissoes(self) -> set[str]:
        """Conjunto de chaves de permissão efetivas (união de todos os papéis)."""
        if self.superadmin:
            return {"*"}
        chaves: set[str] = set()
        for atrib in self.papeis:
            chaves |= atrib.papel.chaves_permissao
        return chaves

    def tem_permissao(self, chave: str) -> bool:
        perms = self.permissoes
        return "*" in perms or chave in perms

    @property
    def nivel_maximo(self) -> int:
        """Maior nível de papel — usado para hierarquia/visibilidade."""
        if self.superadmin:
            return 9999
        return max((a.papel.nivel for a in self.papeis), default=0)

    def setores_no_escopo(self) -> set[int]:
        """IDs de setores onde o usuário tem algum papel (sem expandir subárvore)."""
        return {a.setor_id for a in self.papeis if a.setor_id is not None}

    @property
    def is_active(self) -> bool:  # Flask-Login
        return self.ativo

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.username!r} org={self.organizacao_id}>"
