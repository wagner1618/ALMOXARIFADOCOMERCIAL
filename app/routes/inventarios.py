"""Inventário (§8): abrir, contar item a item, fechar (ajuste/recertificação) e cancelar."""

from __future__ import annotations

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
from app.forms.inventario import AbrirInventarioForm
from app.models.ativo import ESTADOS_CONSERVACAO, ROTULO_ESTADO, ROTULO_STATUS, STATUS_CICLO
from app.models.inventario import STATUS_INVENTARIO, Inventario
from app.models.setor import Setor
from app.security import registrar, requer_permissao
from app.services import inventario_service
from app.services.inventario_service import ErroInventario

bp = Blueprint("inventarios", __name__, url_prefix="/inventarios")


def _org_id() -> int:
    return current_user.organizacao_id


def _inventario_ou_404(inventario_id: int) -> Inventario:
    inv = db.session.get(Inventario, inventario_id)
    if inv is None or inv.organizacao_id != _org_id():
        abort(404)
    return inv


def _choices_setores() -> list[tuple[int, str]]:
    setores = db.session.scalars(
        select(Setor)
        .where(Setor.organizacao_id == _org_id(), Setor.ativo.is_(True))
        .order_by(Setor.path)
    )
    return [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores]


@bp.route("/")
@login_required
@requer_permissao("inventario.realizar")
def listar():
    status = request.args.get("status")
    pagina = request.args.get("page", 1, type=int)
    stmt = select(Inventario).where(Inventario.organizacao_id == _org_id())
    if status in STATUS_INVENTARIO:
        stmt = stmt.where(Inventario.status == status)
    stmt = stmt.order_by(Inventario.numero.desc())
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("inventarios/listar.html", paginacao=paginacao, status=status)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("inventario.realizar")
def novo():
    form = AbrirInventarioForm()
    form.setor_id.choices = _choices_setores()
    if form.validate_on_submit():
        try:
            inv = inventario_service.abrir_inventario(
                _org_id(),
                tipo=form.tipo.data,
                setor_id=form.setor_id.data,
                responsavel_id=current_user.id,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            db.session.flush()
            registrar("inventarios.abrir", entidade="inventario", entidade_id=inv.id)
            db.session.commit()
            flash(f"Inventário #{inv.numero} aberto com {inv.total_itens} itens.", "success")
            return redirect(url_for("inventarios.detalhe", inventario_id=inv.id))
        except ErroInventario as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("inventarios/form.html", form=form, titulo="Novo inventário")


@bp.route("/<int:inventario_id>")
@login_required
@requer_permissao("inventario.realizar")
def detalhe(inventario_id: int):
    inv = _inventario_ou_404(inventario_id)
    return render_template(
        "inventarios/detalhe.html",
        inv=inv,
        estados=[(e, ROTULO_ESTADO[e]) for e in ESTADOS_CONSERVACAO],
        situacoes=[(s, ROTULO_STATUS[s]) for s in STATUS_CICLO],
    )


@bp.route("/<int:inventario_id>/contar", methods=["POST"])
@login_required
@requer_permissao("inventario.realizar")
def contar(inventario_id: int):
    inv = _inventario_ou_404(inventario_id)
    if not inv.aberto:
        flash("Inventário não está em contagem.", "warning")
        return redirect(url_for("inventarios.detalhe", inventario_id=inv.id))
    try:
        for item in inv.itens:
            if inv.is_consumivel:
                valor = request.form.get(f"qtd_{item.id}")
                if valor in (None, ""):
                    continue
                inventario_service.registrar_contagem(
                    item, quantidade=valor.replace(",", "."), commit=False
                )
            else:
                estado = request.form.get(f"estado_{item.id}") or None
                situacao = request.form.get(f"status_{item.id}") or None
                if not estado and not situacao:
                    continue
                inventario_service.registrar_contagem(
                    item, estado_conservacao=estado, status_ciclo=situacao, commit=False
                )
        registrar("inventarios.contar", entidade="inventario", entidade_id=inv.id)
        db.session.commit()
        flash("Contagem salva.", "success")
    except ErroInventario as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("inventarios.detalhe", inventario_id=inv.id))


@bp.route("/<int:inventario_id>/fechar", methods=["POST"])
@login_required
@requer_permissao("inventario.realizar")
def fechar(inventario_id: int):
    inv = _inventario_ou_404(inventario_id)
    try:
        inventario_service.fechar_inventario(inv, usuario_id=current_user.id, commit=False)
        registrar("inventarios.fechar", entidade="inventario", entidade_id=inv.id)
        db.session.commit()
        flash(
            f"Inventário #{inv.numero} fechado ({inv.itens_divergentes} divergências).", "success"
        )
    except ErroInventario as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("inventarios.detalhe", inventario_id=inv.id))


@bp.route("/<int:inventario_id>/cancelar", methods=["POST"])
@login_required
@requer_permissao("inventario.realizar")
def cancelar(inventario_id: int):
    inv = _inventario_ou_404(inventario_id)
    try:
        inventario_service.cancelar_inventario(inv, commit=False)
        registrar("inventarios.cancelar", entidade="inventario", entidade_id=inv.id)
        db.session.commit()
        flash("Inventário cancelado.", "success")
    except ErroInventario as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("inventarios.detalhe", inventario_id=inv.id))
