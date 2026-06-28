"""Camada de segurança: RBAC, escopo de tenant/setor e auditoria."""

from __future__ import annotations

from app.security.auditoria import registrar
from app.security.rbac import requer_permissao, requer_superadmin

__all__ = ["registrar", "requer_permissao", "requer_superadmin"]
