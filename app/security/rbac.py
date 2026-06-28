"""Decorators de autorização: permissão e superadmin."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from flask import abort
from flask_login import current_user

F = TypeVar("F", bound=Callable)


def requer_permissao(*chaves: str) -> Callable[[F], F]:
    """Exige que o usuário tenha PELO MENOS UMA das permissões informadas."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not any(current_user.tem_permissao(c) for c in chaves):
                abort(403)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def requer_superadmin(func: F) -> F:
    """Exige operador da plataforma (acima do tenant)."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "superadmin", False):
            abort(403)
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
