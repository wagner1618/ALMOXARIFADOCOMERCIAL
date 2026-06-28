"""CRUD e ciclo de vida de ativos (patrimônio)."""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from app.extensions import db
from app.forms.ativo import AtivoForm, DestinarForm, RecertificarForm
from app.models.ativo import (
    BAIXADO,
    EM_USO,
    ESTADOS_CONSERVACAO,
    STATUS_CICLO,
    Ativo,
)
from app.models.definicao_campo import ENTIDADE_ATIVO
from app.models.produto import TIPO_DURAVEL, Produto
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.security import registrar, requer_permissao
from app.services import ativo_service
from app.services import campos_customizados as cc
from app.services.ativo_service import ErroAtivo
from app.utils.uploads import ErroUpload, salvar_arquivo

bp = Blueprint("ativos", __name__, url_prefix="/ativos")


def _ativo_da_org(ativo_id: int) -> Ativo:
    ativo = db.session.get(Ativo, ativo_id)
    if ativo is None or ativo.organizacao_id != current_user.organizacao_id:
        abort(404)
    return ativo


def _opcoes_produto() -> list[tuple[int, str]]:
    prods = db.session.scalars(
        select(Produto)
        .where(
            Produto.organizacao_id == current_user.organizacao_id,
            Produto.tipo_controle == TIPO_DURAVEL,
            Produto.ativo.is_(True),
        )
        .order_by(Produto.nome)
    ).all()
    return [(0, "— nenhum —"), *[(p.id, f"{p.sku} · {p.nome}") for p in prods]]


def _opcoes_setor() -> list[tuple[int, str]]:
    setores = db.session.scalars(
        select(Setor)
        .where(Setor.organizacao_id == current_user.organizacao_id, Setor.ativo.is_(True))
        .order_by(Setor.path)
    ).all()
    return [(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores]


def _opcoes_responsavel() -> list[tuple[int, str]]:
    usuarios = db.session.scalars(
        select(Usuario)
        .where(Usuario.organizacao_id == current_user.organizacao_id, Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
    ).all()
    return [(0, "— sem responsável —"), *[(u.id, u.nome) for u in usuarios]]


@bp.route("/")
@login_required
@requer_permissao("ativo.ver")
def listar():
    org_id = current_user.organizacao_id
    busca = request.args.get("q", "").strip()
    status = request.args.get("status")
    estado = request.args.get("estado")
    incluir_baixados = request.args.get("baixados") == "1"
    pagina = request.args.get("page", 1, type=int)

    stmt = select(Ativo).where(Ativo.organizacao_id == org_id)
    if busca:
        like = f"%{busca}%"
        stmt = stmt.where(
            or_(
                Ativo.nome.ilike(like), Ativo.tombamento.ilike(like), Ativo.numero_serie.ilike(like)
            )
        )
    if status in STATUS_CICLO:
        stmt = stmt.where(Ativo.status_ciclo == status)
    if estado in ESTADOS_CONSERVACAO:
        stmt = stmt.where(Ativo.estado_conservacao == estado)
    if not incluir_baixados:
        stmt = stmt.where(Ativo.status_ciclo != BAIXADO)
    stmt = stmt.order_by(Ativo.nome)

    paginacao = db.paginate(stmt, page=pagina, per_page=20, error_out=False)
    return render_template(
        "ativos/listar.html",
        paginacao=paginacao,
        busca=busca,
        status=status,
        estado=estado,
        incluir_baixados=incluir_baixados,
        statuses=STATUS_CICLO,
        estados=ESTADOS_CONSERVACAO,
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def novo():
    form = AtivoForm()
    form.produto_id.choices = _opcoes_produto()
    form.setor_atual_id.choices = _opcoes_setor()
    return _salvar(form, ativo=None)


@bp.route("/<int:ativo_id>/editar", methods=["GET", "POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def editar(ativo_id: int):
    ativo = _ativo_da_org(ativo_id)
    form = AtivoForm(obj=ativo) if request.method == "GET" else AtivoForm()
    form.produto_id.choices = _opcoes_produto()
    form.setor_atual_id.choices = _opcoes_setor()
    if request.method == "GET":
        form.produto_id.data = ativo.produto_id or 0
        form.setor_atual_id.data = ativo.setor_atual_id or 0
    return _salvar(form, ativo=ativo)


def _salvar(form: AtivoForm, *, ativo: Ativo | None):
    org_id = current_user.organizacao_id
    editando = ativo is not None
    produto_id = form.produto_real()
    categoria_id = None
    if produto_id:
        prod = db.session.get(Produto, produto_id)
        categoria_id = prod.categoria_id if prod else None

    definicoes = cc.definicoes_aplicaveis(org_id, ENTIDADE_ATIVO, categoria_id=categoria_id)
    valores_cc = dict(ativo.campos) if editando else {}
    erros_cc: dict[str, str] = {}

    if form.validate_on_submit():
        valores_cc, erros_cc = cc.validar_e_coletar(
            definicoes,
            request.form,
            files=request.files,
            valores_atuais=(ativo.campos if editando else None),
        )
        foto_path = None
        if form.foto.data:
            try:
                foto_path = salvar_arquivo(
                    form.foto.data,
                    subdir="ativos",
                    extensoes_permitidas={".png", ".jpg", ".jpeg", ".webp"},
                )
            except ErroUpload as exc:
                flash(str(exc), "danger")

        if not erros_cc:
            dados = {
                "nome": form.nome.data,
                "produto_id": produto_id,
                "tombamento": form.tombamento.data or None,
                "numero_serie": form.numero_serie.data or None,
                "marca": form.marca.data or None,
                "modelo": form.modelo.data or None,
                "fornecedor": form.fornecedor.data or None,
                "data_aquisicao": form.data_aquisicao.data,
                "valor_aquisicao": form.valor_aquisicao.data,
                "garantia_ate": form.garantia_ate.data,
                "vida_util_meses": form.vida_util_meses.data,
                "valor_residual": form.valor_residual.data,
                "estado_conservacao": form.estado_conservacao.data,
                "setor_atual_id": form.setor_atual_id.data,
                "observacoes": form.observacoes.data or None,
            }
            if foto_path:
                dados["foto"] = foto_path
            try:
                if editando:
                    ativo_service.atualizar_ativo(
                        ativo, dados=dados, campos=valores_cc, commit=False
                    )
                    registrar("ativo.editar", entidade="ativo", entidade_id=ativo.id)
                    msg = "Ativo atualizado."
                else:
                    ativo = ativo_service.criar_ativo(
                        org_id,
                        dados=dados,
                        campos=valores_cc,
                        usuario_id=current_user.id,
                        commit=False,
                    )
                    registrar(
                        "ativo.criar",
                        entidade="ativo",
                        entidade_id=ativo.id,
                        dados_depois={"nome": ativo.nome},
                    )
                    msg = "Ativo cadastrado."
                db.session.commit()
                flash(msg, "success")
                return redirect(url_for("ativos.detalhe", ativo_id=ativo.id))
            except ErroAtivo as exc:
                db.session.rollback()
                flash(str(exc), "danger")

    titulo = f"Editar: {ativo.nome}" if editando else "Novo ativo"
    return render_template(
        "ativos/form.html",
        form=form,
        ativo=ativo,
        titulo=titulo,
        definicoes=definicoes,
        valores_cc=valores_cc,
        erros_cc=erros_cc,
    )


@bp.route("/<int:ativo_id>")
@login_required
@requer_permissao("ativo.ver")
def detalhe(ativo_id: int):
    ativo = _ativo_da_org(ativo_id)
    form_destinar = DestinarForm()
    form_destinar.setor_id.choices = _opcoes_setor()
    form_destinar.responsavel_id.choices = _opcoes_responsavel()
    form_recert = RecertificarForm()
    return render_template(
        "ativos/detalhe.html",
        a=ativo,
        setores=_opcoes_setor(),
        form_destinar=form_destinar,
        form_recert=form_recert,
    )


# ----- Ações de ciclo de vida --------------------------------------------- #
def _acao(ativo_id: int, fn, *, perm: str = "ativo.gerenciar", sucesso: str):
    ativo = _ativo_da_org(ativo_id)
    if not current_user.tem_permissao(perm):
        abort(403)
    try:
        fn(ativo)
        db.session.commit()
        flash(sucesso, "success")
    except ErroAtivo as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("ativos.detalhe", ativo_id=ativo_id))


@bp.route("/<int:ativo_id>/destinar", methods=["POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def destinar(ativo_id: int):
    ativo = _ativo_da_org(ativo_id)
    form = DestinarForm()
    form.setor_id.choices = _opcoes_setor()
    form.responsavel_id.choices = _opcoes_responsavel()
    if form.validate_on_submit():
        try:
            ativo_service.destinar(
                ativo,
                setor_id=form.setor_id.data,
                responsavel_id=form.responsavel_id.data or None,
                usuario_id=current_user.id,
                commit=False,
            )
            registrar(
                "ativo.destinar",
                entidade="ativo",
                entidade_id=ativo.id,
                dados_depois={"setor": form.setor_id.data},
            )
            db.session.commit()
            flash("Ativo destinado (termo de responsabilidade disponível).", "success")
        except ErroAtivo as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("ativos.detalhe", ativo_id=ativo_id))


@bp.route("/<int:ativo_id>/transferir", methods=["POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def transferir(ativo_id: int):
    setor_id = request.form.get("setor_id", type=int)
    return _acao(
        ativo_id,
        lambda a: ativo_service.transferir(
            a, setor_id=setor_id, usuario_id=current_user.id, commit=False
        ),
        sucesso="Ativo transferido.",
    )


@bp.route("/<int:ativo_id>/retornar", methods=["POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def retornar(ativo_id: int):
    return _acao(
        ativo_id,
        lambda a: ativo_service.retornar_estoque(a, usuario_id=current_user.id, commit=False),
        sucesso="Ativo devolvido ao estoque.",
    )


@bp.route("/<int:ativo_id>/manutencao/<acao>", methods=["POST"])
@login_required
@requer_permissao("ativo.gerenciar")
def manutencao(ativo_id: int, acao: str):
    if acao == "enviar":
        return _acao(
            ativo_id,
            lambda a: ativo_service.enviar_manutencao(a, usuario_id=current_user.id, commit=False),
            sucesso="Ativo enviado para manutenção.",
        )
    if acao == "concluir":
        return _acao(
            ativo_id,
            lambda a: ativo_service.concluir_manutencao(
                a, usuario_id=current_user.id, commit=False
            ),
            sucesso="Manutenção concluída.",
        )
    abort(404)


@bp.route("/<int:ativo_id>/baixar", methods=["POST"])
@login_required
@requer_permissao("ativo.baixar")
def baixar(ativo_id: int):
    justificativa = request.form.get("justificativa", "")
    return _acao(
        ativo_id,
        lambda a: ativo_service.baixar(
            a, justificativa=justificativa, usuario_id=current_user.id, commit=False
        ),
        perm="ativo.baixar",
        sucesso="Ativo baixado.",
    )


@bp.route("/<int:ativo_id>/recertificar", methods=["POST"])
@login_required
@requer_permissao("inventario.realizar", "ativo.gerenciar")
def recertificar(ativo_id: int):
    ativo = _ativo_da_org(ativo_id)
    form = RecertificarForm()
    if form.validate_on_submit():
        try:
            ativo_service.recertificar(
                ativo,
                estado_conservacao=form.estado_conservacao.data,
                meses_proxima=form.meses_proxima.data or 12,
                usuario_id=current_user.id,
                commit=False,
            )
            registrar(
                "ativo.recertificar",
                entidade="ativo",
                entidade_id=ativo.id,
                dados_depois={"estado": form.estado_conservacao.data},
            )
            db.session.commit()
            flash("Recertificação registrada.", "success")
        except ErroAtivo as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(url_for("ativos.detalhe", ativo_id=ativo_id))


@bp.route("/<int:ativo_id>/termo")
@login_required
@requer_permissao("ativo.ver")
def termo(ativo_id: int):
    ativo = _ativo_da_org(ativo_id)
    if ativo.status_ciclo != EM_USO:
        flash("O termo de responsabilidade só se aplica a ativos em uso.", "warning")
        return redirect(url_for("ativos.detalhe", ativo_id=ativo_id))
    return render_template("ativos/termo.html", a=ativo)
