"""Documentos (§7.7): busca/download/reimpressão, emissão e edição de modelos."""

from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.documento import ModeloDocumentoForm
from app.models.documento import (
    ROTULO_DOCUMENTO,
    TIPOS_DOCUMENTO,
    Documento,
    ModeloDocumento,
)
from app.models.movimentacao import Movimentacao
from app.models.setor import Setor
from app.security import registrar, requer_permissao
from app.services import documento_service
from app.services.documento_service import ErroDocumento

bp = Blueprint("documentos", __name__, url_prefix="/documentos")


def _org_id() -> int:
    return current_user.organizacao_id


def _doc_ou_404(documento_id: int) -> Documento:
    doc = db.session.get(Documento, documento_id)
    if doc is None or doc.organizacao_id != _org_id():
        abort(404)
    return doc


# --------------------------------------------------------------------------- #
# Busca / listagem
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
@requer_permissao("documento.emitir")
def listar():
    tipo = request.args.get("tipo")
    setor_id = request.args.get("setor", type=int)
    data_de = request.args.get("de")
    data_ate = request.args.get("ate")
    pagina = request.args.get("page", 1, type=int)

    stmt = select(Documento).where(Documento.organizacao_id == _org_id())
    if tipo in TIPOS_DOCUMENTO:
        stmt = stmt.where(Documento.tipo == tipo)
    if setor_id:
        stmt = stmt.where(
            (Documento.setor_origem_id == setor_id) | (Documento.setor_destino_id == setor_id)
        )
    if _data(data_de):
        stmt = stmt.where(Documento.data >= _data(data_de))
    if _data(data_ate):
        stmt = stmt.where(Documento.data <= _data(data_ate))
    stmt = stmt.order_by(Documento.criado_em.desc(), Documento.id.desc())
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)

    setores = db.session.scalars(
        select(Setor).where(Setor.organizacao_id == _org_id()).order_by(Setor.path)
    ).all()
    return render_template(
        "documentos/listar.html",
        paginacao=paginacao,
        tipos=[(t, ROTULO_DOCUMENTO[t]) for t in TIPOS_DOCUMENTO],
        setores=setores,
        tipo=tipo,
        setor_id=setor_id,
        de=data_de,
        ate=data_ate,
    )


def _data(valor: str | None):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date() if valor else None
    except ValueError:
        return None


@bp.route("/<int:documento_id>")
@login_required
@requer_permissao("documento.emitir")
def detalhe(documento_id: int):
    doc = _doc_ou_404(documento_id)
    return render_template("documentos/documento_detalhe.html", doc=doc)


@bp.route("/<int:documento_id>/baixar")
@login_required
@requer_permissao("documento.emitir")
def baixar(documento_id: int):
    return _enviar(documento_id, as_attachment=True)


@bp.route("/<int:documento_id>/reimprimir")
@login_required
@requer_permissao("documento.emitir")
def reimprimir(documento_id: int):
    """Reabre o arquivo armazenado (mesmo hash) para visualização/impressão."""
    return _enviar(documento_id, as_attachment=False)


def _enviar(documento_id: int, *, as_attachment: bool):
    doc = _doc_ou_404(documento_id)
    caminho = documento_service.caminho_arquivo(doc)
    if caminho is None or not caminho.exists():
        abort(404)
    return send_from_directory(
        caminho.parent, caminho.name, as_attachment=as_attachment,
        download_name=f"{doc.numero}.{doc.formato}",
    )


# --------------------------------------------------------------------------- #
# Emissão a partir de uma movimentação
# --------------------------------------------------------------------------- #
@bp.route("/emitir/movimentacao/<int:movimentacao_id>", methods=["POST"])
@login_required
@requer_permissao("documento.emitir")
def emitir_movimentacao(movimentacao_id: int):
    mov = db.session.get(Movimentacao, movimentacao_id)
    if mov is None or mov.organizacao_id != _org_id():
        abort(404)
    if mov.documento_id:
        flash("Esta movimentação já possui documento.", "warning")
        return redirect(url_for("documentos.detalhe", documento_id=mov.documento_id))
    try:
        doc = documento_service.emitir_de_movimentacao(
            mov, emitido_por_id=current_user.id, commit=False
        )
        registrar("documentos.emitir", entidade="documento", entidade_id=doc.id)
        db.session.commit()
        flash(f"Documento {doc.numero} emitido.", "success")
        return redirect(url_for("documentos.detalhe", documento_id=doc.id))
    except ErroDocumento as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("estoque.movimentacoes"))


# --------------------------------------------------------------------------- #
# Modelos de documento
# --------------------------------------------------------------------------- #
@bp.route("/modelos")
@login_required
@requer_permissao("config.organizacao")
def modelos():
    itens = db.session.scalars(
        select(ModeloDocumento)
        .where(ModeloDocumento.organizacao_id == _org_id())
        .order_by(ModeloDocumento.tipo)
    ).all()
    return render_template(
        "documentos/modelos.html", modelos=itens, pdf_ativo=documento_service.pdf_disponivel()
    )


@bp.route("/modelos/<int:modelo_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("config.organizacao")
def modelo_editar(modelo_id: int):
    modelo = db.session.get(ModeloDocumento, modelo_id)
    if modelo is None or modelo.organizacao_id != _org_id():
        abort(404)
    form = ModeloDocumentoForm(obj=modelo)
    if form.validate_on_submit():
        modelo.nome = form.nome.data.strip()
        modelo.conteudo_html = form.conteudo_html.data
        modelo.ativo = form.ativo.data
        registrar("documentos.modelo_editar", entidade="modelo_documento", entidade_id=modelo.id)
        db.session.commit()
        flash("Modelo atualizado.", "success")
        return redirect(url_for("documentos.modelos"))
    return render_template(
        "documentos/modelo_form.html",
        form=form,
        modelo=modelo,
        titulo=f"Modelo — {modelo.rotulo_tipo}",
    )
