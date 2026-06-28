"""Rotas gerais: landing, dashboard e healthcheck."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app.extensions import db
from app.models.ativo import BAIXADO, Ativo
from app.models.movimentacao import Movimentacao
from app.models.produto import Produto
from app.models.setor import Setor
from app.models.transferencia import ENVIADA, RECEBIDA_COM_DIVERGENCIA, Transferencia
from app.models.usuario import Usuario
from app.security import setores_operacionais_ids, setores_visiveis_ids
from app.services import alertas

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
        "ativos": db.session.scalar(
            select(func.count(Ativo.id)).where(
                Ativo.organizacao_id == org_id, Ativo.status_ciclo != BAIXADO
            )
        ),
    }

    revisoes_vencidas = db.session.scalars(
        select(Ativo).where(
            Ativo.organizacao_id == org_id,
            Ativo.status_ciclo != BAIXADO,
            Ativo.proxima_revisao_em.is_not(None),
            Ativo.proxima_revisao_em < date.today(),
        )
    ).all()

    visiveis = setores_visiveis_ids(current_user)
    operacionais = setores_operacionais_ids(current_user)
    itens_alerta = alertas.itens_em_alerta(org_id, setor_ids=visiveis)
    ultimas_mov = db.session.scalars(
        select(Movimentacao)
        .where(Movimentacao.organizacao_id == org_id)
        .order_by(Movimentacao.criado_em.desc(), Movimentacao.id.desc())
        .limit(8)
    ).all()

    pendentes_receber = db.session.scalars(
        select(Transferencia).where(
            Transferencia.organizacao_id == org_id,
            Transferencia.status == ENVIADA,
            Transferencia.setor_destino_id.in_(operacionais or [0]),
        )
    ).all()
    divergencias = db.session.scalars(
        select(Transferencia).where(
            Transferencia.organizacao_id == org_id,
            Transferencia.status == RECEBIDA_COM_DIVERGENCIA,
            Transferencia.setor_origem_id.in_(operacionais or [0]),
        )
    ).all()

    return render_template(
        "dashboard.html",
        cartoes=cartoes,
        itens_alerta=itens_alerta[:8],
        total_alertas=len(itens_alerta),
        ultimas_mov=ultimas_mov,
        pendentes_receber=pendentes_receber,
        divergencias=divergencias,
        revisoes_vencidas=revisoes_vencidas,
    )
