"""Modelos SQLAlchemy. Importar tudo aqui garante registro no metadata."""

from __future__ import annotations

from app.models.auditoria import Auditoria
from app.models.categoria import Categoria
from app.models.localizacao import Localizacao
from app.models.organizacao import Organizacao
from app.models.rbac import Papel, Permissao, UsuarioPapel, papel_permissao
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.models.visibilidade import RegraVisibilidade

__all__ = [
    "Auditoria",
    "Categoria",
    "Localizacao",
    "Organizacao",
    "Papel",
    "Permissao",
    "RegraVisibilidade",
    "Setor",
    "Usuario",
    "UsuarioPapel",
    "papel_permissao",
]
