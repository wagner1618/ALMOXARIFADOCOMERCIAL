"""Admin de definições de campos customizados (§6) — permissão config.campos."""

from __future__ import annotations

import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.campos import DefinicaoCampoForm
from app.models.categoria import Categoria
from app.models.definicao_campo import ENTIDADE_PRODUTO, ENTIDADES, TIPOS_COM_OPCOES, DefinicaoCampo
from app.security import registrar, requer_permissao

bp = Blueprint("definicoes", __name__, url_prefix="/campos")


def _slugify(texto: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", texto.strip().lower()).strip("_")
    return base or "campo"


def _opcoes_categoria() -> list[tuple[int, str]]:
    cats = db.session.scalars(
        select(Categoria)
        .where(Categoria.organizacao_id == current_user.organizacao_id)
        .order_by(Categoria.nome)
    ).all()
    return [(0, "— todas as categorias —"), *[(c.id, c.nome) for c in cats]]


def _definicao_da_org(def_id: int) -> DefinicaoCampo:
    d = db.session.get(DefinicaoCampo, def_id)
    if d is None or d.organizacao_id != current_user.organizacao_id:
        abort(404)
    return d


@bp.route("/")
@login_required
@requer_permissao("config.campos")
def listar():
    entidade = request.args.get("entidade", ENTIDADE_PRODUTO)
    if entidade not in ENTIDADES:
        entidade = ENTIDADE_PRODUTO
    definicoes = db.session.scalars(
        select(DefinicaoCampo)
        .where(
            DefinicaoCampo.organizacao_id == current_user.organizacao_id,
            DefinicaoCampo.entidade == entidade,
        )
        .order_by(DefinicaoCampo.ordem, DefinicaoCampo.rotulo)
    ).all()
    return render_template(
        "definicoes/listar.html", definicoes=definicoes, entidade=entidade, entidades=ENTIDADES
    )


@bp.route("/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("config.campos")
def nova():
    form = DefinicaoCampoForm()
    form.aplica_a_categoria_id.choices = _opcoes_categoria()
    if request.method == "GET":
        form.entidade.data = request.args.get("entidade", ENTIDADE_PRODUTO)

    if form.validate_on_submit():
        chave = _slugify(form.chave.data or form.rotulo.data)
        existe = db.session.scalar(
            select(DefinicaoCampo).where(
                DefinicaoCampo.organizacao_id == current_user.organizacao_id,
                DefinicaoCampo.entidade == form.entidade.data,
                DefinicaoCampo.chave == chave,
            )
        )
        if existe:
            flash(f"Já existe um campo com a chave “{chave}” nessa entidade.", "danger")
        elif form.tipo.data in TIPOS_COM_OPCOES and not form.opcoes_lista():
            flash("Informe ao menos uma opção para campos de seleção.", "danger")
        else:
            d = DefinicaoCampo(
                organizacao_id=current_user.organizacao_id,
                entidade=form.entidade.data,
                chave=chave,
                rotulo=form.rotulo.data.strip(),
                tipo=form.tipo.data,
                opcoes=form.opcoes_lista(),
                obrigatorio=form.obrigatorio.data,
                ordem=form.ordem.data or 0,
                ajuda=form.ajuda.data or None,
                ativo=form.ativo.data,
                aplica_a_categoria_id=form.categoria_real(),
            )
            db.session.add(d)
            registrar(
                "campo.criar",
                entidade="definicao_campo",
                dados_depois={"entidade": d.entidade, "chave": d.chave},
            )
            db.session.commit()
            flash("Campo customizado criado.", "success")
            return redirect(url_for("definicoes.listar", entidade=d.entidade))

    return render_template("definicoes/form.html", form=form, titulo="Novo campo")


@bp.route("/<int:def_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("config.campos")
def editar(def_id: int):
    d = _definicao_da_org(def_id)
    form = DefinicaoCampoForm(obj=d)
    form.aplica_a_categoria_id.choices = _opcoes_categoria()
    if request.method == "GET":
        form.opcoes.data = "\n".join(d.opcoes or [])
        form.aplica_a_categoria_id.data = d.aplica_a_categoria_id or 0

    if form.validate_on_submit():
        if form.tipo.data in TIPOS_COM_OPCOES and not form.opcoes_lista():
            flash("Informe ao menos uma opção para campos de seleção.", "danger")
        else:
            # A chave é imutável após criada (preserva os dados já gravados).
            d.rotulo = form.rotulo.data.strip()
            d.tipo = form.tipo.data
            d.opcoes = form.opcoes_lista()
            d.obrigatorio = form.obrigatorio.data
            d.ordem = form.ordem.data or 0
            d.ajuda = form.ajuda.data or None
            d.ativo = form.ativo.data
            d.aplica_a_categoria_id = form.categoria_real()
            registrar("campo.editar", entidade="definicao_campo", entidade_id=d.id)
            db.session.commit()
            flash("Campo atualizado.", "success")
            return redirect(url_for("definicoes.listar", entidade=d.entidade))

    return render_template(
        "definicoes/form.html", form=form, titulo=f"Editar: {d.rotulo}", definicao=d
    )
