"""CRUD de produtos (catálogo) com campos customizados, busca e paginação."""

from __future__ import annotations

from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.forms.produto import ProdutoForm
from app.models.categoria import Categoria
from app.models.definicao_campo import ENTIDADE_PRODUTO
from app.models.produto import TIPOS_CONTROLE, Produto
from app.security import registrar, requer_permissao
from app.services import campos_customizados as cc
from app.services import excel, produto_service
from app.services.produto_service import ErroProduto
from app.utils.uploads import ErroUpload, salvar_arquivo

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

bp = Blueprint("produtos", __name__, url_prefix="/produtos")


def _produto_da_org(produto_id: int) -> Produto:
    produto = db.session.get(Produto, produto_id)
    if produto is None or produto.organizacao_id != current_user.organizacao_id:
        abort(404)
    return produto


def _opcoes_categoria() -> list[tuple[int, str]]:
    cats = db.session.scalars(
        select(Categoria)
        .where(Categoria.organizacao_id == current_user.organizacao_id, Categoria.ativo.is_(True))
        .order_by(Categoria.nome)
    ).all()
    return [(0, "— sem categoria —"), *[(c.id, c.nome) for c in cats]]


@bp.route("/")
@login_required
@requer_permissao("produto.ver")
def listar():
    org_id = current_user.organizacao_id
    busca = request.args.get("q", "").strip()
    categoria_id = request.args.get("categoria", type=int)
    tipo = request.args.get("tipo")
    incluir_inativos = request.args.get("inativos") == "1"
    pagina = request.args.get("page", 1, type=int)

    stmt = select(Produto).where(Produto.organizacao_id == org_id)
    if busca:
        like = f"%{busca}%"
        stmt = stmt.where(or_(Produto.nome.ilike(like), Produto.sku.ilike(like)))
    if categoria_id:
        stmt = stmt.where(Produto.categoria_id == categoria_id)
    if tipo in TIPOS_CONTROLE:
        stmt = stmt.where(Produto.tipo_controle == tipo)
    if not incluir_inativos:
        stmt = stmt.where(Produto.ativo.is_(True))
    stmt = stmt.order_by(Produto.nome)

    paginacao = db.paginate(stmt, page=pagina, per_page=20, error_out=False)
    return render_template(
        "produtos/listar.html",
        paginacao=paginacao,
        categorias=_opcoes_categoria(),
        busca=busca,
        categoria_id=categoria_id,
        tipo=tipo,
        incluir_inativos=incluir_inativos,
    )


@bp.route("/campos")
@login_required
@requer_permissao("produto.ver")
def campos_por_categoria():
    """Parcial HTMX: campos customizados aplicáveis à categoria selecionada."""
    categoria_id = request.args.get("categoria_id", type=int) or None
    definicoes = cc.definicoes_aplicaveis(
        current_user.organizacao_id, ENTIDADE_PRODUTO, categoria_id=categoria_id
    )
    return render_template("produtos/_campos.html", definicoes=definicoes, valores={}, erros={})


@bp.route("/exportar")
@login_required
@requer_permissao("produto.ver")
def exportar():
    incluir_inativos = request.args.get("inativos") == "1"
    dados = excel.exportar_produtos(current_user.organizacao_id, incluir_inativos=incluir_inativos)
    nome = f"produtos_{datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(
        dados,
        mimetype=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename={nome}"},
    )


@bp.route("/modelo")
@login_required
@requer_permissao("produto.criar")
def modelo_importacao():
    dados = excel.gerar_modelo_importacao()
    return Response(
        dados,
        mimetype=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=modelo_importacao_produtos.xlsx"},
    )


@bp.route("/importar", methods=["GET", "POST"])
@login_required
@requer_permissao("produto.criar")
def importar():
    resultado = None
    if request.method == "POST":
        arquivo = request.files.get("planilha")
        if not arquivo or not arquivo.filename:
            flash("Selecione uma planilha .xlsx.", "danger")
        else:
            try:
                resultado = excel.importar_produtos(current_user.organizacao_id, arquivo.read())
                registrar(
                    "produto.importar",
                    entidade="produto",
                    dados_depois={
                        "criados": resultado["criados"],
                        "atualizados": resultado["atualizados"],
                    },
                )
                db.session.commit()
                flash(
                    f"Importação concluída: {resultado['criados']} criados, "
                    f"{resultado['atualizados']} atualizados, {len(resultado['erros'])} com erro.",
                    "success" if not resultado["erros"] else "warning",
                )
            except Exception as exc:
                db.session.rollback()
                flash(f"Não foi possível ler a planilha: {exc}", "danger")
    return render_template("produtos/importar.html", resultado=resultado)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("produto.criar")
def novo():
    form = ProdutoForm()
    form.categoria_id.choices = _opcoes_categoria()
    return _salvar(form, produto=None)


@bp.route("/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("produto.criar")
def editar(produto_id: int):
    produto = _produto_da_org(produto_id)
    form = ProdutoForm(obj=produto) if request.method == "GET" else ProdutoForm()
    form.categoria_id.choices = _opcoes_categoria()
    if request.method == "GET":
        form.categoria_id.data = produto.categoria_id or 0
    return _salvar(form, produto=produto)


def _salvar(form: ProdutoForm, *, produto: Produto | None):
    org_id = current_user.organizacao_id
    editando = produto is not None
    erros_cc: dict[str, str] = {}
    valores_cc: dict = dict(produto.campos) if editando else {}

    if form.validate_on_submit():
        categoria_id = form.categoria_real()
        definicoes = cc.definicoes_aplicaveis(org_id, ENTIDADE_PRODUTO, categoria_id=categoria_id)
        valores_cc, erros_cc = cc.validar_e_coletar(
            definicoes,
            request.form,
            files=request.files,
            valores_atuais=(produto.campos if editando else None),
        )

        foto_path = None
        if form.foto.data:
            try:
                foto_path = salvar_arquivo(
                    form.foto.data,
                    subdir="produtos",
                    extensoes_permitidas={".png", ".jpg", ".jpeg", ".webp"},
                )
            except ErroUpload as exc:
                flash(str(exc), "danger")

        if not erros_cc:
            try:
                if editando:
                    produto_service.atualizar_produto(
                        produto,
                        dados={
                            "nome": form.nome.data,
                            "sku": form.sku.data,
                            "tipo_controle": form.tipo_controle.data,
                            "categoria_id": categoria_id,
                            "unidade": form.unidade.data,
                            "estoque_minimo": form.estoque_minimo.data or 0,
                            "estoque_maximo": form.estoque_maximo.data,
                            "marca": form.marca.data,
                            "modelo": form.modelo.data,
                            "valor_unitario_referencia": form.valor_unitario_referencia.data,
                            "descricao": form.descricao.data,
                            "ativo": form.ativo.data,
                            "campos": valores_cc,
                            "foto": foto_path,
                        },
                        commit=False,
                    )
                    registrar("produto.editar", entidade="produto", entidade_id=produto.id)
                    msg = "Produto atualizado."
                else:
                    produto = produto_service.criar_produto(
                        org_id,
                        nome=form.nome.data,
                        tipo_controle=form.tipo_controle.data,
                        sku=form.sku.data,
                        categoria_id=categoria_id,
                        unidade=form.unidade.data,
                        estoque_minimo=form.estoque_minimo.data or 0,
                        estoque_maximo=form.estoque_maximo.data,
                        marca=form.marca.data,
                        modelo=form.modelo.data,
                        valor_unitario_referencia=form.valor_unitario_referencia.data,
                        descricao=form.descricao.data,
                        foto=foto_path,
                        campos=valores_cc,
                        commit=False,
                    )
                    registrar(
                        "produto.criar",
                        entidade="produto",
                        entidade_id=produto.id,
                        dados_depois={"nome": produto.nome},
                    )
                    msg = f"Produto criado (SKU {produto.sku})."
                db.session.commit()
                flash(msg, "success")
                return redirect(url_for("produtos.listar"))
            except ErroProduto as exc:
                db.session.rollback()
                flash(str(exc), "danger")

    definicoes = cc.definicoes_aplicaveis(
        org_id,
        ENTIDADE_PRODUTO,
        categoria_id=(form.categoria_real() if form.categoria_id.data else None),
    )
    titulo = f"Editar: {produto.nome}" if editando else "Novo produto"
    return render_template(
        "produtos/form.html",
        form=form,
        produto=produto,
        titulo=titulo,
        definicoes=definicoes,
        valores_cc=valores_cc,
        erros_cc=erros_cc,
    )
