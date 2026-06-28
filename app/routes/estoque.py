"""Estoque de consumíveis: posição, entrada, saída, lote e histórico."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.forms.estoque import AjusteForm, EntradaForm, SaidaForm
from app.models.estoque import SaldoEstoque
from app.models.movimentacao import (
    ENTRADA,
    SAIDA,
    TIPOS_MOVIMENTACAO,
    Movimentacao,
)
from app.models.produto import TIPO_CONSUMIVEL, Produto
from app.models.setor import Setor
from app.security import registrar, requer_permissao, setores_operacionais_ids, setores_visiveis_ids
from app.services import alertas, estoque_service
from app.services.estoque_service import ErroEstoque

bp = Blueprint("estoque", __name__, url_prefix="/estoque")


def _produtos_consumiveis() -> list[Produto]:
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


def _choices_produtos() -> list[tuple[int, str]]:
    return [(p.id, f"{p.sku} · {p.nome} ({p.unidade})") for p in _produtos_consumiveis()]


def _setores_por_ids(ids: set[int]) -> list[Setor]:
    if not ids:
        return []
    return list(
        db.session.scalars(
            select(Setor).where(Setor.id.in_(ids), Setor.ativo.is_(True)).order_by(Setor.path)
        )
    )


def _choices_setores_operacionais() -> list[tuple[int, str]]:
    setores = _setores_por_ids(setores_operacionais_ids(current_user))
    return [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores]


# --------------------------------------------------------------------------- #
# Posição de estoque
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
@requer_permissao("produto.ver")
def posicao():
    org_id = current_user.organizacao_id
    visiveis = setores_visiveis_ids(current_user)
    busca = request.args.get("q", "").strip()
    setor_id = request.args.get("setor", type=int)
    pagina = request.args.get("page", 1, type=int)

    stmt = (
        select(SaldoEstoque)
        .join(Produto, SaldoEstoque.produto_id == Produto.id)
        .where(SaldoEstoque.organizacao_id == org_id)
        .where(SaldoEstoque.setor_id.in_(visiveis or [0]))
    )
    if setor_id:
        stmt = stmt.where(SaldoEstoque.setor_id == setor_id)
    if busca:
        like = f"%{busca}%"
        stmt = stmt.where(or_(Produto.nome.ilike(like), Produto.sku.ilike(like)))
    stmt = stmt.order_by(Produto.nome)

    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    setores = _setores_por_ids(visiveis)
    total_alertas = alertas.contar_alertas(org_id, setor_ids=visiveis)
    return render_template(
        "estoque/posicao.html",
        paginacao=paginacao,
        setores=setores,
        busca=busca,
        setor_id=setor_id,
        total_alertas=total_alertas,
    )


# --------------------------------------------------------------------------- #
# Entrada / Saída
# --------------------------------------------------------------------------- #
@bp.route("/entrada", methods=["GET", "POST"])
@login_required
@requer_permissao("movimentacao.entrada")
def entrada():
    form = EntradaForm()
    form.produto_id.choices = _choices_produtos()
    form.setor_id.choices = _choices_setores_operacionais()

    if form.validate_on_submit():
        if not _pode_atuar(form.setor_id.data):
            abort(403)
        try:
            mov = estoque_service.entrada(
                current_user.organizacao_id,
                produto_id=form.produto_id.data,
                setor_id=form.setor_id.data,
                quantidade=form.quantidade.data,
                valor_unitario=form.valor_unitario.data,
                usuario_id=current_user.id,
                observacoes=form.observacoes.data,
                commit=False,
            )
            registrar(
                "estoque.entrada",
                entidade="movimentacao",
                entidade_id=mov.id,
                dados_depois={"produto": form.produto_id.data, "qtd": str(form.quantidade.data)},
            )
            db.session.commit()
            flash("Entrada registrada.", "success")
            return redirect(url_for("estoque.posicao"))
        except ErroEstoque as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "estoque/movimento.html", form=form, titulo="Entrada de estoque", tipo="ENTRADA"
    )


@bp.route("/saida", methods=["GET", "POST"])
@login_required
@requer_permissao("movimentacao.saida")
def saida():
    form = SaidaForm()
    form.produto_id.choices = _choices_produtos()
    form.setor_id.choices = _choices_setores_operacionais()

    if form.validate_on_submit():
        if not _pode_atuar(form.setor_id.data):
            abort(403)
        try:
            mov = estoque_service.saida(
                current_user.organizacao_id,
                produto_id=form.produto_id.data,
                setor_id=form.setor_id.data,
                quantidade=form.quantidade.data,
                destinatario=form.destinatario.data,
                usuario_id=current_user.id,
                observacoes=form.observacoes.data,
                commit=False,
            )
            registrar(
                "estoque.saida",
                entidade="movimentacao",
                entidade_id=mov.id,
                dados_depois={"produto": form.produto_id.data, "qtd": str(form.quantidade.data)},
            )
            db.session.commit()
            flash("Saída registrada.", "success")
            return redirect(url_for("estoque.posicao"))
        except ErroEstoque as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "estoque/movimento.html", form=form, titulo="Saída de estoque", tipo="SAIDA"
    )


# --------------------------------------------------------------------------- #
# Lançamento em lote
# --------------------------------------------------------------------------- #
@bp.route("/lote", methods=["GET", "POST"])
@login_required
@requer_permissao("movimentacao.entrada", "movimentacao.saida")
def lote():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        if tipo not in (ENTRADA, SAIDA):
            flash("Tipo de lote inválido.", "danger")
            return redirect(url_for("estoque.lote"))

        perm = "movimentacao.entrada" if tipo == ENTRADA else "movimentacao.saida"
        if not current_user.tem_permissao(perm):
            abort(403)

        produtos = request.form.getlist("produto_id")
        setores = request.form.getlist("setor_id")
        quantidades = request.form.getlist("quantidade")
        valores = request.form.getlist("valor_unitario")

        operacoes = []
        for i, prod in enumerate(produtos):
            if not prod or not quantidades[i]:
                continue
            setor_id = int(setores[i])
            if not _pode_atuar(setor_id):
                abort(403)
            op = {
                "tipo": tipo,
                "produto_id": int(prod),
                "setor_id": setor_id,
                "quantidade": quantidades[i].replace(",", "."),
            }
            if tipo == ENTRADA and i < len(valores) and valores[i]:
                op["valor_unitario"] = valores[i].replace(",", ".")
            operacoes.append(op)

        try:
            lote_obj = estoque_service.processar_lote(
                current_user.organizacao_id,
                operacoes=operacoes,
                usuario_id=current_user.id,
                observacoes=request.form.get("observacoes") or None,
            )
            registrar(
                "estoque.lote",
                entidade="lote_movimentacao",
                entidade_id=lote_obj.id,
                dados_depois={"tipo": tipo, "linhas": len(operacoes)},
            )
            db.session.commit()
            flash(f"Lote #{lote_obj.numero} processado ({len(operacoes)} linhas).", "success")
            return redirect(url_for("estoque.movimentacoes"))
        except ErroEstoque as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "estoque/lote.html",
        produtos=_choices_produtos(),
        setores=_choices_setores_operacionais(),
    )


# --------------------------------------------------------------------------- #
# Ajuste de inventário (rápido, por saldo)
# --------------------------------------------------------------------------- #
@bp.route("/ajuste/<int:produto_id>/<int:setor_id>", methods=["GET", "POST"])
@login_required
@requer_permissao("inventario.realizar")
def ajuste(produto_id: int, setor_id: int):
    if not _pode_atuar(setor_id):
        abort(403)
    saldo = estoque_service.obter_saldo(produto_id, setor_id)
    produto = db.session.get(Produto, produto_id)
    if produto is None or produto.organizacao_id != current_user.organizacao_id:
        abort(404)

    form = AjusteForm()
    if request.method == "GET" and saldo:
        form.nova_quantidade.data = saldo.quantidade

    if form.validate_on_submit():
        try:
            estoque_service.ajustar(
                current_user.organizacao_id,
                produto_id=produto_id,
                setor_id=setor_id,
                nova_quantidade=form.nova_quantidade.data,
                justificativa=form.justificativa.data,
                usuario_id=current_user.id,
                commit=False,
            )
            registrar(
                "estoque.ajuste",
                entidade="produto",
                entidade_id=produto_id,
                dados_depois={"setor": setor_id, "qtd": str(form.nova_quantidade.data)},
            )
            db.session.commit()
            flash("Saldo ajustado.", "success")
            return redirect(url_for("estoque.posicao"))
        except ErroEstoque as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("estoque/ajuste.html", form=form, produto=produto, saldo=saldo)


# --------------------------------------------------------------------------- #
# Histórico de movimentações (append-only)
# --------------------------------------------------------------------------- #
@bp.route("/movimentacoes")
@login_required
@requer_permissao("produto.ver")
def movimentacoes():
    org_id = current_user.organizacao_id
    tipo = request.args.get("tipo")
    produto_id = request.args.get("produto", type=int)
    pagina = request.args.get("page", 1, type=int)

    stmt = select(Movimentacao).where(Movimentacao.organizacao_id == org_id)
    if tipo in TIPOS_MOVIMENTACAO:
        stmt = stmt.where(Movimentacao.tipo == tipo)
    if produto_id:
        stmt = stmt.where(Movimentacao.produto_id == produto_id)
    stmt = stmt.order_by(Movimentacao.criado_em.desc(), Movimentacao.id.desc())

    paginacao = db.paginate(stmt, page=pagina, per_page=30, error_out=False)
    return render_template(
        "estoque/movimentacoes.html",
        paginacao=paginacao,
        tipo=tipo,
        produtos=_choices_produtos(),
        produto_id=produto_id,
        tipos=TIPOS_MOVIMENTACAO,
    )


@bp.route("/alertas")
@login_required
@requer_permissao("produto.ver")
def lista_alertas():
    itens = alertas.itens_em_alerta(
        current_user.organizacao_id, setor_ids=setores_visiveis_ids(current_user)
    )
    return render_template("estoque/alertas.html", itens=itens)


def _pode_atuar(setor_id: int) -> bool:
    return setor_id in setores_operacionais_ids(current_user)
