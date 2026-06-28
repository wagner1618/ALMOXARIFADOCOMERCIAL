"""Helper para registrar trilha de auditoria (append-only)."""

from __future__ import annotations

from typing import Any

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models.auditoria import Auditoria


def registrar(
    acao: str,
    *,
    entidade: str | None = None,
    entidade_id: int | None = None,
    dados_antes: dict[str, Any] | None = None,
    dados_depois: dict[str, Any] | None = None,
    organizacao_id: int | None = None,
    usuario_id: int | None = None,
    commit: bool = False,
) -> Auditoria:
    """Cria um registro de auditoria. Por padrão não faz commit (entra na transação)."""
    if has_request_context():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_agent = request.user_agent.string[:255] if request.user_agent else None
    else:
        ip = user_agent = None

    if usuario_id is None and getattr(current_user, "is_authenticated", False):
        usuario_id = current_user.id
        organizacao_id = organizacao_id or getattr(current_user, "organizacao_id", None)

    log = Auditoria(
        organizacao_id=organizacao_id,
        usuario_id=usuario_id,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
        ip=ip,
        user_agent=user_agent,
    )
    db.session.add(log)
    if commit:
        db.session.commit()
    return log
