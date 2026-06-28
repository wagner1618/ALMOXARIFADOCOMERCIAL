"""Transferências entre setores com confirmação (§7.8)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.models.produto import TIPO_CONSUMIVEL, Produto
from app.models.setor import Setor
from app.models.transferencia import (
    ENVIADA,
    RECEBIDA_COM_DIVERGENCIA,
    STATUS_TRANSFERENCIA,
    Transferencia,
)
from app.security import registrar, requer_permissao, setores_operacionais_ids
from app.services import transferencia_service
from app.services.transferencia_service import ErroTransferencia

bp = Blueprint("transferencias", __name__, url_prefix="/transferencias")


def _transferencia_da_org(transf_id: int) -> Transferencia:
    transf = db.session.get(Transferencia, transf_id)
    if transf is None or transf.organizacao_id != current_user.organizacao_id:
        abort(404)
    return transf


def _setores_por_ids(ids: set[int]) -> list[Setor]:
    if not ids:
        return []
    return list(
        db.session.scalars(
            select(Setor).where(Setor.id.in_(ids), Setor.ativo.is_(True)).order_by(Setor.path)
        )
    )


def _todos_setores() -> list[Setor]:
    return list(
        db.session.scalars(
            select(Setor)
            .where(Setor.organizacao_id == current_user.organizacao_id, Setor.ativo.is_(True))
            .order_by(Setor.path)
        )
    )


def _consumiveis() -> list[Produto]:
    return list(
        db.session.scalars(
            select(Produto)
            .where(
                Produto.organizacao_id == current_user.organizacao_id,
                Produto.tipo_controle == TIPO_CONSUMIVEL,
                Produto.ativo.is_(True),
            )
            .order_by(Produto.nome)
        )
    )


@bp.route("/")
@login_required
@requer_permissao("transferencia.enviar", "transferencia.receber")
def listar():
    org_id = current_user.organizacao_id
    operacionais = setores_operacionais_ids(current_user)
    status = request.args.get("status")
    pagina = request.args.get("page", 1, type=int)

    stmt = select(Transferencia).where(Transferencia.organizacao_id == org_id)
    # Só transferências que tocam o escopo do usuário (origem ou destino).
    if operacionais:
        stmt = stmt.where(
            or_(
                Transferencia.setor_origem_id.in_(operacionais),
                Transferencia.setor_destino_id.in_(operacionais),
            )
        )
    else:
        stmt = stmt.where(Transferencia.id == 0)
    if status in STATUS_TRANSFERENCIA:
        stmt = stmt.where(Transferencia.status == status)
    stmt = stmt.order_by(Transferencia.criado_em.desc())

    paginacao = db.paginate(stmt, page=pagina, per_page=20, error_out=False)
    # Pendências de recebimento no destino do usuário.
    pendentes = db.session.scalars(
        select(Transferencia).where(
            Transferencia.organizacao_id == org_id,
            Transferencia.status == ENVIADA,
            Transferencia.setor_destino_id.in_(operacionais or [0]),
        )
    ).all()
    return render_template(
        "transferencias/listar.html",
        paginacao=paginacao,
        status=status,
        statuses=STATUS_TRANSFERENCIA,
        pendentes=pendentes,
    )


@bp.route("/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("transferencia.enviar")
def nova():
    operacionais = setores_operacionais_ids(current_user)
    setores_origem = _setores_por_ids(operacionais)

    if request.method == "POST":
        origem_id = request.form.get("setor_origem_id", type=int)
        destino_id = request.form.get("setor_destino_id", type=int)
        if origem_id not in operacionais:
            abort(403)

        produtos = request.form.getlist("produto_id")
        quantidades = request.form.getlist("quantidade")
        itens = [
            {"produto_id": int(p), "quantidade": quantidades[i].replace(",", ".")}
            for i, p in enumerate(produtos)
            if p and i < len(quantidades) and quantidades[i]
        ]
        try:
            transf = transferencia_service.enviar(
                current_user.organizacao_id,
                setor_origem_id=origem_id,
                setor_destino_id=destino_id,
                itens=itens,
                usuario_id=current_user.id,
                observacoes=request.form.get("observacoes") or None,
            )
            registrar(
                "transferencia.enviar",
                entidade="transferencia",
                entidade_id=transf.id,
                dados_depois={"numero": transf.numero, "itens": len(itens)},
            )
            db.session.commit()
            flash(f"Transferência #{transf.numero} enviada (em trânsito).", "success")
            return redirect(url_for("transferencias.detalhe", transf_id=transf.id))
        except ErroTransferencia as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "transferencias/nova.html",
        setores_origem=setores_origem,
        setores_destino=_todos_setores(),
        produtos=_consumiveis(),
    )


@bp.route("/<int:transf_id>")
@login_required
@requer_permissao("transferencia.enviar", "transferencia.receber")
def detalhe(transf_id: int):
    transf = _transferencia_da_org(transf_id)
    operacionais = setores_operacionais_ids(current_user)
    pode_receber = (
        transf.status == ENVIADA
        and transf.setor_destino_id in operacionais
        and current_user.tem_permissao("transferencia.receber")
    )
    pode_corrigir = (
        transf.status == RECEBIDA_COM_DIVERGENCIA
        and transf.setor_origem_id in operacionais
        and current_user.tem_permissao("transferencia.corrigir")
    )
    pode_cancelar = (
        transf.status == ENVIADA
        and transf.setor_origem_id in operacionais
        and current_user.tem_permissao("transferencia.enviar")
    )
    return render_template(
        "transferencias/detalhe.html",
        t=transf,
        pode_receber=pode_receber,
        pode_corrigir=pode_corrigir,
        pode_cancelar=pode_cancelar,
    )


@bp.route("/<int:transf_id>/receber", methods=["GET", "POST"])
@login_required
@requer_permissao("transferencia.receber")
def receber(transf_id: int):
    transf = _transferencia_da_org(transf_id)
    if transf.setor_destino_id not in setores_operacionais_ids(current_user):
        abort(403)
    if transf.status != ENVIADA:
        flash("Esta transferência não está aguardando recebimento.", "warning")
        return redirect(url_for("transferencias.detalhe", transf_id=transf.id))

    if request.method == "POST":
        recebimentos = {}
        for item in transf.itens:
            qtd = request.form.get(f"recebida_{item.id}", "").replace(",", ".")
            motivo = request.form.get(f"motivo_{item.id}") or None
            recebimentos[item.id] = {
                "quantidade_recebida": qtd if qtd else 0,
                "motivo": motivo,
            }
        try:
            transferencia_service.receber(
                transf,
                recebimentos=recebimentos,
                usuario_id=current_user.id,
                observacoes=request.form.get("observacoes") or None,
            )
            registrar(
                "transferencia.receber",
                entidade="transferencia",
                entidade_id=transf.id,
                dados_depois={"status": transf.status},
            )
            db.session.commit()
            flash("Recebimento confirmado.", "success")
            return redirect(url_for("transferencias.detalhe", transf_id=transf.id))
        except ErroTransferencia as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("transferencias/receber.html", t=transf)


@bp.route("/<int:transf_id>/corrigir", methods=["POST"])
@login_required
@requer_permissao("transferencia.corrigir")
def corrigir(transf_id: int):
    transf = _transferencia_da_org(transf_id)
    if transf.setor_origem_id not in setores_operacionais_ids(current_user):
        abort(403)
    try:
        transferencia_service.corrigir(
            transf,
            usuario_id=current_user.id,
            observacao=request.form.get("observacao") or None,
        )
        registrar("transferencia.corrigir", entidade="transferencia", entidade_id=transf.id)
        db.session.commit()
        flash("Divergência corrigida (pendência estornada à origem).", "success")
    except ErroTransferencia as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("transferencias.detalhe", transf_id=transf.id))


@bp.route("/<int:transf_id>/cancelar", methods=["POST"])
@login_required
@requer_permissao("transferencia.enviar")
def cancelar(transf_id: int):
    transf = _transferencia_da_org(transf_id)
    if transf.setor_origem_id not in setores_operacionais_ids(current_user):
        abort(403)
    try:
        transferencia_service.cancelar(transf, usuario_id=current_user.id)
        registrar("transferencia.cancelar", entidade="transferencia", entidade_id=transf.id)
        db.session.commit()
        flash("Transferência cancelada e reservas estornadas.", "info")
    except ErroTransferencia as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("transferencias.detalhe", transf_id=transf.id))
