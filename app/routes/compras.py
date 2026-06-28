"""Compras (§7.9): fornecedores, pedidos de compra e notas fiscais valoradas."""

from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.forms.compras import FornecedorForm, NotaFiscalForm, PedidoForm
from app.models.compras import (
    APROVADO,
    EMPENHADO,
    STATUS_PEDIDO,
    NotaFiscal,
    PedidoCompra,
)
from app.models.fornecedor import Fornecedor
from app.models.produto import Produto
from app.models.setor import Setor
from app.security import registrar, requer_permissao, setores_operacionais_ids
from app.services import compra_service
from app.services.compra_service import ErroCompra
from app.utils.uploads import ErroUpload, salvar_arquivo

bp = Blueprint("compras", __name__, url_prefix="/compras")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _setores_compra() -> list[Setor]:
    """Setores com poder de compra dentro do escopo operacional do usuário."""
    operacionais = setores_operacionais_ids(current_user)
    if not operacionais:
        return []
    return list(
        db.session.scalars(
            select(Setor)
            .where(
                Setor.organizacao_id == current_user.organizacao_id,
                Setor.id.in_(operacionais),
                Setor.poder_compra.is_(True),
                Setor.ativo.is_(True),
            )
            .order_by(Setor.path)
        )
    )


def _choices_setores_compra() -> list[tuple[int, str]]:
    return [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in _setores_compra()]


def _fornecedores_ativos() -> list[Fornecedor]:
    return list(
        db.session.scalars(
            select(Fornecedor)
            .where(
                Fornecedor.organizacao_id == current_user.organizacao_id,
                Fornecedor.ativo.is_(True),
            )
            .order_by(Fornecedor.nome)
        )
    )


def _choices_fornecedores(opcional: bool = True) -> list[tuple[int, str]]:
    itens = [
        (f.id, f"{f.nome}{f' · {f.documento}' if f.documento else ''}")
        for f in _fornecedores_ativos()
    ]
    return [(0, "— sem fornecedor —"), *itens] if opcional else itens


def _choices_produtos() -> list[tuple[int, str]]:
    produtos = db.session.scalars(
        select(Produto)
        .where(Produto.organizacao_id == current_user.organizacao_id, Produto.ativo.is_(True))
        .order_by(Produto.nome)
    )
    return [(0, "— item avulso —")] + [(p.id, f"{p.sku} · {p.nome}") for p in produtos]


def _parse_itens() -> list[dict]:
    """Lê as linhas dinâmicas de itens (pedido/NF) do formulário."""
    produtos = request.form.getlist("item_produto_id")
    descricoes = request.form.getlist("item_descricao")
    quantidades = request.form.getlist("item_quantidade")
    valores = request.form.getlist("item_valor_unitario")
    itens: list[dict] = []
    for i, qtd in enumerate(quantidades):
        produto_id = int(produtos[i]) if i < len(produtos) and produtos[i] else 0
        descricao = descricoes[i] if i < len(descricoes) else ""
        if not qtd and not produto_id and not (descricao or "").strip():
            continue
        itens.append(
            {
                "produto_id": produto_id or None,
                "descricao": descricao,
                "quantidade": (qtd or "0").replace(",", "."),
                "valor_unitario": (valores[i] if i < len(valores) else "0").replace(",", "."),
            }
        )
    return itens


def _pedido_ou_404(pedido_id: int) -> PedidoCompra:
    pedido = db.session.get(PedidoCompra, pedido_id)
    if pedido is None or pedido.organizacao_id != current_user.organizacao_id:
        abort(404)
    return pedido


def _nota_ou_404(nota_id: int) -> NotaFiscal:
    nota = db.session.get(NotaFiscal, nota_id)
    if nota is None or nota.organizacao_id != current_user.organizacao_id:
        abort(404)
    return nota


# --------------------------------------------------------------------------- #
# Fornecedores
# --------------------------------------------------------------------------- #
@bp.route("/fornecedores")
@login_required
@requer_permissao("fornecedor.gerenciar")
def fornecedores():
    busca = request.args.get("q", "").strip()
    pagina = request.args.get("page", 1, type=int)
    stmt = select(Fornecedor).where(Fornecedor.organizacao_id == current_user.organizacao_id)
    if busca:
        like = f"%{busca}%"
        stmt = stmt.where(or_(Fornecedor.nome.ilike(like), Fornecedor.documento.ilike(like)))
    stmt = stmt.order_by(Fornecedor.nome)
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("compras/fornecedores.html", paginacao=paginacao, busca=busca)


@bp.route("/fornecedores/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("fornecedor.gerenciar")
def fornecedor_novo():
    form = FornecedorForm()
    if form.validate_on_submit():
        try:
            forn = compra_service.criar_fornecedor(
                current_user.organizacao_id, dados=_dados_fornecedor(form), commit=False
            )
            db.session.flush()
            registrar("compras.fornecedor_criar", entidade="fornecedor", entidade_id=forn.id)
            db.session.commit()
            flash("Fornecedor cadastrado.", "success")
            return redirect(url_for("compras.fornecedores"))
        except ErroCompra as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("compras/fornecedor_form.html", form=form, titulo="Novo fornecedor")


@bp.route("/fornecedores/<int:fornecedor_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("fornecedor.gerenciar")
def fornecedor_editar(fornecedor_id: int):
    forn = db.session.get(Fornecedor, fornecedor_id)
    if forn is None or forn.organizacao_id != current_user.organizacao_id:
        abort(404)
    form = FornecedorForm(obj=forn)
    if form.validate_on_submit():
        try:
            compra_service.atualizar_fornecedor(forn, dados=_dados_fornecedor(form), commit=False)
            registrar("compras.fornecedor_editar", entidade="fornecedor", entidade_id=forn.id)
            db.session.commit()
            flash("Fornecedor atualizado.", "success")
            return redirect(url_for("compras.fornecedores"))
        except ErroCompra as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "compras/fornecedor_form.html", form=form, titulo=f"Editar — {forn.nome}"
    )


def _dados_fornecedor(form: FornecedorForm) -> dict:
    return {
        "nome": form.nome.data.strip(),
        "tipo_pessoa": form.tipo_pessoa.data,
        "documento": form.documento.data,
        "inscricao_estadual": form.inscricao_estadual.data or None,
        "contato": form.contato.data or None,
        "email": form.email.data or None,
        "telefone": form.telefone.data or None,
        "endereco": form.endereco.data or None,
        "observacoes": form.observacoes.data or None,
    }


# --------------------------------------------------------------------------- #
# Pedidos de compra
# --------------------------------------------------------------------------- #
@bp.route("/pedidos")
@login_required
@requer_permissao("compra.pedido", "compra.aprovar")
def pedidos():
    status = request.args.get("status")
    pagina = request.args.get("page", 1, type=int)
    stmt = select(PedidoCompra).where(PedidoCompra.organizacao_id == current_user.organizacao_id)
    if status in STATUS_PEDIDO:
        stmt = stmt.where(PedidoCompra.status == status)
    stmt = stmt.order_by(PedidoCompra.numero.desc())
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template(
        "compras/pedidos.html", paginacao=paginacao, status=status, status_opcoes=STATUS_PEDIDO
    )


@bp.route("/pedidos/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("compra.pedido")
def pedido_novo():
    form = PedidoForm()
    form.setor_id.choices = _choices_setores_compra()
    form.fornecedor_id.choices = _choices_fornecedores()
    if form.validate_on_submit():
        try:
            pedido = compra_service.criar_pedido(
                current_user.organizacao_id,
                setor_id=form.setor_id.data,
                fornecedor_id=form.fornecedor_id.data or None,
                itens=_parse_itens(),
                justificativa=form.justificativa.data or None,
                observacoes=form.observacoes.data or None,
                solicitante_id=current_user.id,
                commit=False,
            )
            db.session.flush()
            registrar("compras.pedido_criar", entidade="pedido_compra", entidade_id=pedido.id)
            db.session.commit()
            flash(f"Pedido #{pedido.numero} criado.", "success")
            return redirect(url_for("compras.pedido_detalhe", pedido_id=pedido.id))
        except ErroCompra as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "compras/pedido_form.html",
        form=form,
        titulo="Novo pedido de compra",
        produtos=_choices_produtos(),
        itens=[],
    )


@bp.route("/pedidos/<int:pedido_id>")
@login_required
@requer_permissao("compra.pedido", "compra.aprovar")
def pedido_detalhe(pedido_id: int):
    pedido = _pedido_ou_404(pedido_id)
    situacao = compra_service.checar_orcamento(pedido.setor, pedido.exercicio, 0)
    return render_template("compras/pedido_detalhe.html", pedido=pedido, situacao=situacao)


@bp.route("/pedidos/<int:pedido_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("compra.pedido")
def pedido_editar(pedido_id: int):
    pedido = _pedido_ou_404(pedido_id)
    if not pedido.editavel:
        flash("Apenas pedidos em rascunho podem ser editados.", "warning")
        return redirect(url_for("compras.pedido_detalhe", pedido_id=pedido.id))
    form = PedidoForm(obj=pedido)
    form.setor_id.choices = _choices_setores_compra()
    form.fornecedor_id.choices = _choices_fornecedores()
    if request.method == "GET":
        form.fornecedor_id.data = pedido.fornecedor_id or 0
    if form.validate_on_submit():
        try:
            compra_service.atualizar_pedido(
                pedido,
                fornecedor_id=form.fornecedor_id.data or None,
                itens=_parse_itens(),
                justificativa=form.justificativa.data or None,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            registrar("compras.pedido_editar", entidade="pedido_compra", entidade_id=pedido.id)
            db.session.commit()
            flash("Pedido atualizado.", "success")
            return redirect(url_for("compras.pedido_detalhe", pedido_id=pedido.id))
        except ErroCompra as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "compras/pedido_form.html",
        form=form,
        titulo=f"Editar pedido #{pedido.numero}",
        produtos=_choices_produtos(),
        itens=pedido.itens,
    )


@bp.route("/pedidos/<int:pedido_id>/<acao>", methods=["POST"])
@login_required
def pedido_transicao(pedido_id: int, acao: str):
    pedido = _pedido_ou_404(pedido_id)
    operacoes = {
        "aprovar": ("compra.aprovar", compra_service.aprovar_pedido, "Pedido aprovado."),
        "empenhar": ("compra.aprovar", compra_service.empenhar_pedido, "Pedido empenhado."),
        "concluir": ("compra.aprovar", compra_service.concluir_pedido, "Pedido concluído."),
        "cancelar": ("compra.pedido", compra_service.cancelar_pedido, "Pedido cancelado."),
    }
    if acao not in operacoes:
        abort(404)
    perm, funcao, msg = operacoes[acao]
    if not current_user.tem_permissao(perm):
        abort(403)
    try:
        kwargs = {"aprovador_id": current_user.id} if acao == "aprovar" else {}
        funcao(pedido, commit=False, **kwargs)
        registrar(f"compras.pedido_{acao}", entidade="pedido_compra", entidade_id=pedido.id)
        db.session.commit()
        flash(msg, "success")
    except ErroCompra as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("compras.pedido_detalhe", pedido_id=pedido.id))


# --------------------------------------------------------------------------- #
# Notas fiscais
# --------------------------------------------------------------------------- #
@bp.route("/notas")
@login_required
@requer_permissao("compra.nota_fiscal", "compra.entrada_valorada")
def notas():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(NotaFiscal)
        .where(NotaFiscal.organizacao_id == current_user.organizacao_id)
        .order_by(NotaFiscal.criado_em.desc(), NotaFiscal.id.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("compras/notas.html", paginacao=paginacao)


@bp.route("/notas/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("compra.nota_fiscal")
def nota_nova():
    form = NotaFiscalForm()
    form.fornecedor_id.choices = _choices_fornecedores(opcional=False)
    form.setor_id.choices = _choices_setores_compra()
    form.pedido_id.choices = [(0, "— nenhum —")] + [
        (p.id, f"#{p.numero} ({p.rotulo_status})")
        for p in db.session.scalars(
            select(PedidoCompra)
            .where(
                PedidoCompra.organizacao_id == current_user.organizacao_id,
                PedidoCompra.status.in_((APROVADO, EMPENHADO)),
            )
            .order_by(PedidoCompra.numero.desc())
        )
    ]
    if form.validate_on_submit():
        try:
            pdf = _salvar_anexo(form.arquivo_pdf.data)
            xml = _salvar_anexo(form.arquivo_xml.data)
            nota = compra_service.registrar_nota(
                current_user.organizacao_id,
                fornecedor_id=form.fornecedor_id.data,
                setor_id=form.setor_id.data,
                numero=form.numero.data,
                serie=form.serie.data,
                chave_nfe=form.chave_nfe.data,
                pedido_id=form.pedido_id.data or None,
                data_emissao=form.data_emissao.data,
                data_entrada=form.data_entrada.data,
                itens=_parse_itens(),
                arquivo_pdf=pdf,
                arquivo_xml=xml,
                observacoes=form.observacoes.data or None,
                usuario_id=current_user.id,
                commit=False,
            )
            db.session.flush()
            registrar("compras.nota_registrar", entidade="nota_fiscal", entidade_id=nota.id)
            db.session.commit()
            flash(f"Nota fiscal {nota.numero} registrada.", "success")
            return redirect(url_for("compras.nota_detalhe", nota_id=nota.id))
        except (ErroCompra, ErroUpload) as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "compras/nota_form.html", form=form, produtos=_choices_produtos(), titulo="Nova nota fiscal"
    )


@bp.route("/notas/<int:nota_id>")
@login_required
@requer_permissao("compra.nota_fiscal", "compra.entrada_valorada")
def nota_detalhe(nota_id: int):
    nota = _nota_ou_404(nota_id)
    return render_template("compras/nota_detalhe.html", nota=nota)


@bp.route("/notas/<int:nota_id>/lancar", methods=["POST"])
@login_required
@requer_permissao("compra.entrada_valorada")
def nota_lancar(nota_id: int):
    nota = _nota_ou_404(nota_id)
    try:
        compra_service.lancar_entrada_valorada(nota, usuario_id=current_user.id, commit=False)
        registrar("compras.nota_lancar", entidade="nota_fiscal", entidade_id=nota.id)
        db.session.commit()
        flash("Entrada valorada lançada a partir da nota fiscal.", "success")
    except ErroCompra as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("compras.nota_detalhe", nota_id=nota.id))


@bp.route("/notas/<int:nota_id>/anexo/<tipo>")
@login_required
@requer_permissao("compra.nota_fiscal", "compra.entrada_valorada")
def nota_anexo(nota_id: int, tipo: str):
    nota = _nota_ou_404(nota_id)
    caminho = nota.arquivo_pdf if tipo == "pdf" else nota.arquivo_xml if tipo == "xml" else None
    if not caminho:
        abort(404)
    base = Path(current_app.config["UPLOAD_DIR"])
    return send_from_directory(base, caminho, as_attachment=True)


def _salvar_anexo(arquivo) -> str | None:
    if not arquivo or not getattr(arquivo, "filename", ""):
        return None
    return salvar_arquivo(arquivo, subdir="notas", extensoes_permitidas={".pdf", ".xml"})
