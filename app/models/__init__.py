"""Modelos SQLAlchemy. Importar tudo aqui garante registro no metadata."""

from __future__ import annotations

from app.models.auditoria import Auditoria
from app.models.organizacao import Organizacao
from app.models.rbac import Papel, Permissao, UsuarioPapel, papel_permissao
from app.models.setor import Setor
from app.models.usuario import Usuario

__all__ = [
    "Auditoria",
    "Organizacao",
    "Papel",
    "Permissao",
    "Setor",
    "Usuario",
    "UsuarioPapel",
    "papel_permissao",
]
