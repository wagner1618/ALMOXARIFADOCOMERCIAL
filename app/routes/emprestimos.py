"""Empréstimos (§7.5): emprestar/devolver consumíveis e duráveis, vencidos e recibos."""

from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.emprestimo import TIPO_DURAVEL, EmprestimoForm
from app.models.ativo import EM_ESTOQUE, EM_USO, Ativo
from app.models.emprestimo import EM_ABERTO, Emprestimo
from app.models.produto import Produto
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.security import registrar, requer_permissao
from app.services import emprestimo_service
from app.services.emprestimo_service import ErroEmprestimo

bp = Blueprint("emprestimos", __name__, url_prefix="/emprestimos")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _org_id() -> int:
    return current_user.organizacao_id


def _choices_produtos() -> list[tuple[int, str]]:
    produtos = db.session.scalars(
        select(Produto)
        .where(
            Produto.organizacao_id == _org_id(),
            Produto.ativo.is_(True),
            Produto.tipo_controle == "CONSUMIVEL",
        )
        .order_by(Produto.nome)
    )
    return [(0, "— selecione —")] + [(p.id, f"{p.sku} · {p.nome}") for p in produtos]


def _choices_ativos() -> list[tuple[int, str]]:
    ativos = db.session.scalars(
        select(Ativo)
        .where(
            Ativo.organizacao_id == _org_id(),
            Ativo.ativo.is_(True),
            Ativo.status_ciclo.in_((EM_ESTOQUE, EM_USO)),
        )
        .order_by(Ativo.nome)
    )
    return [(0, "— selecione —")] + [
        (a.id, f"{a.tombamento or a.id} · {a.nome}") for a in ativos
    ]


def _choices_setores() -> list[tuple[int, str]]:
    setores = db.session.scalars(
        select(Setor)
        .where(Setor.organizacao_id == _org_id(), Setor.ativo.is_(True))
        .order_by(Setor.path)
    )
    return [(0, "— selecione —")] + [
        (s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores
    ]


def _choices_usuarios() -> list[tuple[int, str]]:
    usuarios = db.session.scalars(
        select(Usuario)
        .where(Usuario.organizacao_id == _org_id(), Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
    )
    return [(0, "— ninguém —")] + [(u.id, u.nome) for u in usuarios]


def _emprestimo_ou_404(emprestimo_id: int) -> Emprestimo:
    emp = db.session.get(Emprestimo, emprestimo_id)
    if emp is None or emp.organizacao_id != _org_id():
        abort(404)
    return emp


# --------------------------------------------------------------------------- #
# Listagem
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
@requer_permissao("emprestimo.gerenciar")
def listar():
    filtro = request.args.get("filtro", "abertos")
    pagina = request.args.get("page", 1, type=int)
    stmt = select(Emprestimo).where(Emprestimo.organizacao_id == _org_id())
    if filtro == "vencidos":
        stmt = stmt.where(
            Emprestimo.status.in_(EM_ABERTO), Emprestimo.data_prevista < date.today()
        )
    elif filtro == "devolvidos":
        stmt = stmt.where(Emprestimo.status == "DEVOLVIDO")
    else:  # abertos
        stmt = stmt.where(Emprestimo.status.in_(EM_ABERTO))
    stmt = stmt.order_by(
        Emprestimo.data_prevista.is_(None), Emprestimo.data_prevista, Emprestimo.id.desc()
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("emprestimos/listar.html", paginacao=paginacao, filtro=filtro)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("emprestimo.gerenciar")
def novo():
    form = EmprestimoForm()
    form.produto_id.choices = _choices_produtos()
    form.ativo_id.choices = _choices_ativos()
    form.setor_id.choices = _choices_setores()
    form.responsavel_id.choices = _choices_usuarios()
    if form.validate_on_submit():
        try:
            duravel = form.tipo.data == TIPO_DURAVEL
            emp = emprestimo_service.emprestar(
                _org_id(),
                produto_id=None if duravel else (form.produto_id.data or None),
                ativo_id=(form.ativo_id.data or None) if duravel else None,
                setor_id=form.setor_id.data or None,
                quantidade=(form.quantidade.data or "1").replace(",", "."),
                destinatario=form.destinatario.data or None,
                responsavel_id=form.responsavel_id.data or None,
                data_prevista=form.data_prevista.data,
                observacoes=form.observacoes.data or None,
                usuario_id=current_user.id,
                commit=False,
            )
            db.session.flush()
            registrar("emprestimos.emprestar", entidade="emprestimo", entidade_id=emp.id)
            db.session.commit()
            flash("Empréstimo registrado.", "success")
            return redirect(url_for("emprestimos.listar"))
        except ErroEmprestimo as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("emprestimos/form.html", form=form, titulo="Novo empréstimo")


@bp.route("/<int:emprestimo_id>/devolver", methods=["POST"])
@login_required
@requer_permissao("emprestimo.gerenciar")
def devolver(emprestimo_id: int):
    emp = _emprestimo_ou_404(emprestimo_id)
    quantidade = request.form.get("quantidade")
    try:
        emprestimo_service.devolver(
            emp,
            quantidade=(quantidade.replace(",", ".") if quantidade else None),
            usuario_id=current_user.id,
            commit=False,
        )
        registrar("emprestimos.devolver", entidade="emprestimo", entidade_id=emp.id)
        db.session.commit()
        flash("Devolução registrada.", "success")
    except ErroEmprestimo as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("emprestimos.listar", filtro=request.args.get("filtro", "abertos")))


@bp.route("/recibos")
@login_required
@requer_permissao("emprestimo.gerenciar")
def recibos():
    """Recibo/termo imprimível dos empréstimos em aberto, agrupado por setor."""
    abertos = emprestimo_service.emprestimos_em_aberto(_org_id())
    grupos: dict[int | None, list[Emprestimo]] = {}
    for emp in abertos:
        grupos.setdefault(emp.setor_id, []).append(emp)
    setores = {
        s.id: s.nome
        for s in db.session.scalars(
            select(Setor).where(Setor.organizacao_id == _org_id())
        )
    }
    return render_template(
        "emprestimos/recibos.html", grupos=grupos, setores=setores, hoje=date.today()
    )
