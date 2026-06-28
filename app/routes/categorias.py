"""CRUD de categorias (por organização)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.cadastros import CategoriaForm
from app.models.categoria import Categoria
from app.security import registrar, requer_permissao

bp = Blueprint("categorias", __name__, url_prefix="/categorias")


def _categoria_da_org(categoria_id: int) -> Categoria:
    cat = db.session.get(Categoria, categoria_id)
    if cat is None or cat.organizacao_id != current_user.organizacao_id:
        abort(404)
    return cat


@bp.route("/")
@login_required
@requer_permissao("setor.gerenciar", "produto.criar")
def listar():
    categorias = db.session.scalars(
        select(Categoria)
        .where(Categoria.organizacao_id == current_user.organizacao_id)
        .order_by(Categoria.nome)
    ).all()
    return render_template("categorias/listar.html", categorias=categorias)


@bp.route("/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar", "produto.criar")
def nova():
    form = CategoriaForm()
    if form.validate_on_submit():
        existe = db.session.scalar(
            select(Categoria).where(
                Categoria.organizacao_id == current_user.organizacao_id,
                db.func.lower(Categoria.nome) == form.nome.data.strip().lower(),
            )
        )
        if existe:
            flash("Já existe uma categoria com esse nome.", "danger")
        else:
            cat = Categoria(
                organizacao_id=current_user.organizacao_id,
                nome=form.nome.data.strip(),
                descricao=form.descricao.data or None,
                ativo=form.ativo.data,
            )
            db.session.add(cat)
            registrar("categoria.criar", entidade="categoria", dados_depois={"nome": cat.nome})
            db.session.commit()
            flash("Categoria criada.", "success")
            return redirect(url_for("categorias.listar"))
    return render_template("categorias/form.html", form=form, titulo="Nova categoria")


@bp.route("/<int:categoria_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar", "produto.criar")
def editar(categoria_id: int):
    cat = _categoria_da_org(categoria_id)
    form = CategoriaForm(obj=cat)
    if form.validate_on_submit():
        cat.nome = form.nome.data.strip()
        cat.descricao = form.descricao.data or None
        cat.ativo = form.ativo.data
        registrar("categoria.editar", entidade="categoria", entidade_id=cat.id)
        db.session.commit()
        flash("Categoria atualizada.", "success")
        return redirect(url_for("categorias.listar"))
    return render_template("categorias/form.html", form=form, titulo=f"Editar: {cat.nome}")
