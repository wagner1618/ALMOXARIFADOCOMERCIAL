"""CRUD de localizações físicas (dentro de um setor)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.cadastros import LocalizacaoForm
from app.models.localizacao import Localizacao
from app.security import registrar, requer_permissao
from app.services import setor_service

bp = Blueprint("localizacoes", __name__, url_prefix="/localizacoes")


def _opcoes_setor():
    setores = setor_service.listar_setores(current_user.organizacao_id, apenas_ativos=True)
    return [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores]


def _localizacao_da_org(loc_id: int) -> Localizacao:
    loc = db.session.get(Localizacao, loc_id)
    if loc is None or loc.organizacao_id != current_user.organizacao_id:
        abort(404)
    return loc


@bp.route("/")
@login_required
@requer_permissao("setor.gerenciar")
def listar():
    locs = db.session.scalars(
        select(Localizacao)
        .where(Localizacao.organizacao_id == current_user.organizacao_id)
        .order_by(Localizacao.setor_id, Localizacao.nome)
    ).all()
    nomes_setor = {s.id: s.nome for s in setor_service.listar_setores(current_user.organizacao_id)}
    return render_template("localizacoes/listar.html", localizacoes=locs, nomes_setor=nomes_setor)


@bp.route("/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar")
def nova():
    form = LocalizacaoForm()
    form.setor_id.choices = _opcoes_setor()
    if form.validate_on_submit():
        loc = Localizacao(
            organizacao_id=current_user.organizacao_id,
            setor_id=form.setor_id.data,
            nome=form.nome.data.strip(),
            descricao=form.descricao.data or None,
            ativo=form.ativo.data,
        )
        db.session.add(loc)
        registrar("localizacao.criar", entidade="localizacao", dados_depois={"nome": loc.nome})
        db.session.commit()
        flash("Localização criada.", "success")
        return redirect(url_for("localizacoes.listar"))
    return render_template("localizacoes/form.html", form=form, titulo="Nova localização")


@bp.route("/<int:loc_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar")
def editar(loc_id: int):
    loc = _localizacao_da_org(loc_id)
    form = LocalizacaoForm(obj=loc)
    form.setor_id.choices = _opcoes_setor()
    if form.validate_on_submit():
        loc.setor_id = form.setor_id.data
        loc.nome = form.nome.data.strip()
        loc.descricao = form.descricao.data or None
        loc.ativo = form.ativo.data
        registrar("localizacao.editar", entidade="localizacao", entidade_id=loc.id)
        db.session.commit()
        flash("Localização atualizada.", "success")
        return redirect(url_for("localizacoes.listar"))
    return render_template("localizacoes/form.html", form=form, titulo=f"Editar: {loc.nome}")
