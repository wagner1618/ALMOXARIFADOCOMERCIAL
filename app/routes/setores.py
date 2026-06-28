"""CRUD de setores (árvore) e configuração de visibilidade entre setores."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.cadastros import RegraVisibilidadeForm, SetorForm
from app.models.setor import Setor
from app.models.visibilidade import RegraVisibilidade
from app.security import registrar, requer_permissao
from app.services import setor_service
from app.services.setor_service import ErroSetor

bp = Blueprint("setores", __name__, url_prefix="/setores")


def _setor_da_org(setor_id: int) -> Setor:
    setor = db.session.get(Setor, setor_id)
    if setor is None or setor.organizacao_id != current_user.organizacao_id:
        abort(404)
    return setor


def _opcoes_pai(excluir: Setor | None = None) -> list[tuple[int, str]]:
    """Setores candidatos a pai. Ao editar, remove o próprio e a subárvore."""
    setores = setor_service.listar_setores(current_user.organizacao_id)
    proibidos: set[int] = set()
    if excluir is not None:
        proibidos = setor_service.ids_subarvore(excluir)
    opcoes = [(0, "— (setor raiz) —")]
    for s in setores:
        if s.id in proibidos:
            continue
        prefixo = "  " * (s.nivel - 1)
        opcoes.append((s.id, f"{prefixo}{s.nome}"))
    return opcoes


@bp.route("/")
@login_required
@requer_permissao("setor.gerenciar")
def listar():
    nos = setor_service.arvore(current_user.organizacao_id)
    return render_template("setores/listar.html", nos=nos)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar")
def novo():
    form = SetorForm()
    form.setor_pai_id.choices = _opcoes_pai()
    pai_pre = request.args.get("pai", type=int)
    if request.method == "GET" and pai_pre:
        form.setor_pai_id.data = pai_pre

    if form.validate_on_submit():
        try:
            setor = setor_service.criar_setor(
                current_user.organizacao_id,
                nome=form.nome.data,
                codigo=form.codigo.data,
                setor_pai_id=form.setor_pai_real(),
                poder_compra=form.poder_compra.data,
                centro_custo=form.centro_custo.data,
                orcamento_anual=form.orcamento_anual.data,
                permite_visualizacao_externa=form.permite_visualizacao_externa.data,
                commit=False,
            )
            registrar(
                "setor.criar",
                entidade="setor",
                entidade_id=setor.id,
                dados_depois={"nome": setor.nome},
            )
            db.session.commit()
            flash(f"Setor “{setor.nome}” criado.", "success")
            return redirect(url_for("setores.listar"))
        except (ErroSetor, ValueError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template("setores/form.html", form=form, titulo="Novo setor")


@bp.route("/<int:setor_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("setor.gerenciar")
def editar(setor_id: int):
    setor = _setor_da_org(setor_id)
    form = SetorForm(obj=setor)
    form.setor_pai_id.choices = _opcoes_pai(excluir=setor)
    if request.method == "GET":
        form.setor_pai_id.data = setor.setor_pai_id or 0

    if form.validate_on_submit():
        antes = {"nome": setor.nome, "pai": setor.setor_pai_id}
        try:
            setor_service.atualizar_setor(
                setor,
                dados={
                    "nome": form.nome.data,
                    "codigo": form.codigo.data or None,
                    "setor_pai_id": form.setor_pai_real(),
                    "poder_compra": form.poder_compra.data,
                    "centro_custo": form.centro_custo.data or None,
                    "orcamento_anual": form.orcamento_anual.data,
                    "permite_visualizacao_externa": form.permite_visualizacao_externa.data,
                    "ativo": form.ativo.data,
                },
                commit=False,
            )
            registrar(
                "setor.editar",
                entidade="setor",
                entidade_id=setor.id,
                dados_antes=antes,
                dados_depois={"nome": setor.nome},
            )
            db.session.commit()
            flash("Setor atualizado.", "success")
            return redirect(url_for("setores.listar"))
        except (ErroSetor, ValueError) as exc:
            db.session.rollback()
            flash(str(exc), "danger")

    return render_template(
        "setores/form.html", form=form, titulo=f"Editar: {setor.nome}", setor=setor
    )


@bp.route("/<int:setor_id>/inativar", methods=["POST"])
@login_required
@requer_permissao("setor.gerenciar")
def inativar(setor_id: int):
    setor = _setor_da_org(setor_id)
    em_cascata = request.form.get("cascata") == "1"
    setor_service.inativar_setor(setor, em_cascata=em_cascata, commit=False)
    registrar(
        "setor.inativar",
        entidade="setor",
        entidade_id=setor.id,
        dados_depois={"cascata": em_cascata},
    )
    db.session.commit()
    flash(f"Setor “{setor.nome}” inativado.", "warning")
    return redirect(url_for("setores.listar"))


# --------------------------------------------------------------------------- #
# Visibilidade entre setores (§8.3)
# --------------------------------------------------------------------------- #
@bp.route("/visibilidade", methods=["GET", "POST"])
@login_required
@requer_permissao("config.visibilidade")
def visibilidade():
    org_id = current_user.organizacao_id
    setores = setor_service.listar_setores(org_id)
    escolhas = [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores]

    form = RegraVisibilidadeForm()
    form.setor_observador_id.choices = escolhas
    form.setor_alvo_id.choices = escolhas

    if form.validate_on_submit():
        obs, alvo = form.setor_observador_id.data, form.setor_alvo_id.data
        if obs == alvo:
            flash("O setor observador e o alvo devem ser diferentes.", "danger")
        elif db.session.scalar(
            select(RegraVisibilidade).where(
                RegraVisibilidade.organizacao_id == org_id,
                RegraVisibilidade.setor_observador_id == obs,
                RegraVisibilidade.setor_alvo_id == alvo,
            )
        ):
            flash("Essa regra de visibilidade já existe.", "warning")
        else:
            regra = RegraVisibilidade(
                organizacao_id=org_id,
                setor_observador_id=obs,
                setor_alvo_id=alvo,
                inclui_subarvore=form.inclui_subarvore.data,
            )
            db.session.add(regra)
            registrar(
                "visibilidade.criar",
                entidade="regra_visibilidade",
                dados_depois={"observador": obs, "alvo": alvo},
            )
            db.session.commit()
            flash("Regra de visibilidade adicionada.", "success")
        return redirect(url_for("setores.visibilidade"))

    regras = db.session.scalars(
        select(RegraVisibilidade)
        .where(RegraVisibilidade.organizacao_id == org_id)
        .order_by(RegraVisibilidade.criado_em.desc())
    ).all()
    nomes = {s.id: s.nome for s in setores}
    return render_template("setores/visibilidade.html", form=form, regras=regras, nomes=nomes)


@bp.route("/visibilidade/<int:regra_id>/remover", methods=["POST"])
@login_required
@requer_permissao("config.visibilidade")
def remover_visibilidade(regra_id: int):
    regra = db.session.get(RegraVisibilidade, regra_id)
    if regra is None or regra.organizacao_id != current_user.organizacao_id:
        abort(404)
    db.session.delete(regra)
    registrar("visibilidade.remover", entidade="regra_visibilidade", entidade_id=regra_id)
    db.session.commit()
    flash("Regra removida.", "info")
    return redirect(url_for("setores.visibilidade"))
