"""Camada de segurança: RBAC, escopo de tenant/setor e auditoria."""

from __future__ import annotations

from app.security.auditoria import registrar
from app.security.escopo import (
    pode_atuar_no_setor,
    pode_ver_setor,
    setores_operacionais_ids,
    setores_visiveis_ids,
)
from app.security.rbac import requer_permissao, requer_superadmin

__all__ = [
    "pode_atuar_no_setor",
    "pode_ver_setor",
    "registrar",
    "requer_permissao",
    "requer_superadmin",
    "setores_operacionais_ids",
    "setores_visiveis_ids",
]
