"""Rotas gerais: landing, dashboard e healthcheck."""

from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app.extensions import db
from app.models.produto import Produto
from app.models.setor import Setor
from app.models.usuario import Usuario

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/healthz")
def healthz():
    """Healthcheck para orquestradores (Docker/Nginx)."""
    try:
        db.session.execute(select(1))
        return jsonify(status="ok"), 200
    except Exception:  # pragma: no cover - falha de banco
        return jsonify(status="degraded"), 503


@bp.route("/dashboard")
@login_required
def dashboard():
    org_id = current_user.organizacao_id
    cartoes = {
        "usuarios": db.session.scalar(
            select(func.count(Usuario.id)).where(Usuario.organizacao_id == org_id)
        ),
        "setores": db.session.scalar(
            select(func.count(Setor.id)).where(Setor.organizacao_id == org_id)
        ),
        "produtos": db.session.scalar(
            select(func.count(Produto.id)).where(
                Produto.organizacao_id == org_id, Produto.ativo.is_(True)
            )
        ),
        # Placeholder da próxima fase (ativos/patrimônio).
        "ativos": None,
    }
    return render_template("dashboard.html", cartoes=cartoes)
