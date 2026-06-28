"""Compras públicas (§7.10, Lei 14.133/2021) — só no modo PÚBLICO.

Cadeia da despesa: dotação → processo → ata/contrato → empenho → recebimento →
liquidação → pagamento. Cada etapa consome saldos validados pelo ``publico_service``.
O blueprint inteiro fica indisponível (404) quando a organização está em modo PRIVADO.
"""

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
from app.forms.publico import (
    STATUS_PROCESSO_CHOICES,
    AditivoForm,
    AtaForm,
    ContratoForm,
    DotacaoForm,
    EmpenhoForm,
    LiquidacaoForm,
    PagamentoForm,
    ProcessoForm,
    RecebimentoForm,
)
from app.models.compras import NotaFiscal
from app.models.fornecedor import Fornecedor
from app.models.produto import Produto
from app.models.publico import (
    MODALIDADES,
    RECEB_DEFINITIVO,
    ROTULO_MODALIDADE,
    STATUS_PROCESSO,
    AtaRegistroPrecos,
    Contrato,
    DotacaoOrcamentaria,
    Empenho,
    Liquidacao,
    ProcessoContratacao,
    Recebimento,
)
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.security import registrar, requer_permissao
from app.services import publico_service
from app.services.publico_service import ErroPublico

PUBLICO = "PUBLICO"

bp = Blueprint("publico", __name__, url_prefix="/publico")


@bp.before_request
def _exige_modo_publico():
    """Bloqueia o módulo inteiro fora do modo PÚBLICO (§7.10)."""
    if current_user.is_authenticated:
        org = current_user.organizacao
        if org is None or org.modo_compra != PUBLICO:
            abort(404)


# --------------------------------------------------------------------------- #
# Helpers de choices / parsing
# --------------------------------------------------------------------------- #
def _org_id() -> int:
    return current_user.organizacao_id


def _opc(itens: list[tuple[int, str]], vazio: str = "— nenhum —") -> list[tuple[int, str]]:
    return [(0, vazio), *itens]


def _choices_fornecedores(opcional: bool = True) -> list[tuple[int, str]]:
    fornecedores = db.session.scalars(
        select(Fornecedor)
        .where(Fornecedor.organizacao_id == _org_id(), Fornecedor.ativo.is_(True))
        .order_by(Fornecedor.nome)
    )
    itens = [(f.id, f"{f.nome}{f' · {f.documento}' if f.documento else ''}") for f in fornecedores]
    return _opc(itens, "— selecione —") if opcional else itens


def _choices_usuarios() -> list[tuple[int, str]]:
    usuarios = db.session.scalars(
        select(Usuario)
        .where(Usuario.organizacao_id == _org_id(), Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
    )
    return _opc([(u.id, u.nome) for u in usuarios])


def _choices_setores() -> list[tuple[int, str]]:
    setores = db.session.scalars(
        select(Setor)
        .where(Setor.organizacao_id == _org_id(), Setor.ativo.is_(True))
        .order_by(Setor.path)
    )
    return _opc([(s.id, ("  " * (s.nivel - 1)) + s.nome) for s in setores])


def _choices_processos() -> list[tuple[int, str]]:
    processos = db.session.scalars(
        select(ProcessoContratacao)
        .where(ProcessoContratacao.organizacao_id == _org_id())
        .order_by(ProcessoContratacao.numero_processo)
    )
    return _opc([(p.id, f"{p.numero_processo} · {p.rotulo_modalidade}") for p in processos])


def _choices_atas() -> list[tuple[int, str]]:
    atas = db.session.scalars(
        select(AtaRegistroPrecos)
        .where(AtaRegistroPrecos.organizacao_id == _org_id())
        .order_by(AtaRegistroPrecos.numero)
    )
    return _opc([(a.id, f"{a.numero} · {a.fornecedor.nome}") for a in atas])


def _choices_contratos() -> list[tuple[int, str]]:
    contratos = db.session.scalars(
        select(Contrato).where(Contrato.organizacao_id == _org_id()).order_by(Contrato.numero)
    )
    return _opc([(c.id, f"{c.numero} · {c.fornecedor.nome}") for c in contratos])


def _choices_dotacoes() -> list[tuple[int, str]]:
    dotacoes = db.session.scalars(
        select(DotacaoOrcamentaria)
        .where(DotacaoOrcamentaria.organizacao_id == _org_id())
        .order_by(DotacaoOrcamentaria.exercicio.desc(), DotacaoOrcamentaria.id.desc())
    )
    rotulos = []
    for d in dotacoes:
        nome = d.descricao or d.programa_trabalho or f"Dotação {d.id}"
        rotulos.append((d.id, f"{nome} · saldo {d.saldo_disponivel}"))
    return rotulos


def _choices_notas() -> list[tuple[int, str]]:
    notas = db.session.scalars(
        select(NotaFiscal)
        .where(NotaFiscal.organizacao_id == _org_id())
        .order_by(NotaFiscal.criado_em.desc())
    )
    return _opc(
        [(n.id, f"NF {n.numero} · {n.fornecedor.nome if n.fornecedor else '—'}") for n in notas]
    )


def _choices_empenhos() -> list[tuple[int, str]]:
    empenhos = db.session.scalars(
        select(Empenho).where(Empenho.organizacao_id == _org_id()).order_by(Empenho.numero)
    )
    return _opc([(e.id, f"{e.numero} · {e.valor}") for e in empenhos])


def _choices_recebimentos_definitivos() -> list[tuple[int, str]]:
    recebimentos = db.session.scalars(
        select(Recebimento)
        .where(
            Recebimento.organizacao_id == _org_id(),
            Recebimento.tipo == RECEB_DEFINITIVO,
        )
        .order_by(Recebimento.id.desc())
    )
    return _opc([(r.id, f"#{r.id} · {r.data}") for r in recebimentos])


def _choices_produtos() -> list[tuple[int, str]]:
    produtos = db.session.scalars(
        select(Produto)
        .where(Produto.organizacao_id == _org_id(), Produto.ativo.is_(True))
        .order_by(Produto.nome)
    )
    return [(0, "— item avulso —")] + [(p.id, f"{p.sku} · {p.nome}") for p in produtos]


def _parse_itens() -> list[dict]:
    """Lê as linhas dinâmicas de itens (ata/contrato) do formulário."""
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


def _num(valor) -> str | None:
    """Normaliza vírgula decimal de campos monetários StringField."""
    if valor in (None, ""):
        return None
    return str(valor).replace(",", ".")


def _ou_404(modelo, ident: int):
    obj = db.session.get(modelo, ident)
    if obj is None or obj.organizacao_id != _org_id():
        abort(404)
    return obj


# --------------------------------------------------------------------------- #
# Dotações orçamentárias
# --------------------------------------------------------------------------- #
@bp.route("/dotacoes")
@login_required
@requer_permissao("dotacao.gerenciar")
def dotacoes():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(DotacaoOrcamentaria)
        .where(DotacaoOrcamentaria.organizacao_id == _org_id())
        .order_by(DotacaoOrcamentaria.exercicio.desc(), DotacaoOrcamentaria.id.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("publico/dotacoes.html", paginacao=paginacao)


@bp.route("/dotacoes/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("dotacao.gerenciar")
def dotacao_nova():
    form = DotacaoForm()
    if form.validate_on_submit():
        try:
            dot = publico_service.criar_dotacao(
                _org_id(),
                dados={
                    "exercicio": form.exercicio.data,
                    "descricao": form.descricao.data or None,
                    "programa_trabalho": form.programa_trabalho.data or None,
                    "natureza_despesa": form.natureza_despesa.data or None,
                    "fonte_recurso": form.fonte_recurso.data or None,
                    "unidade_orcamentaria": form.unidade_orcamentaria.data or None,
                    "valor_dotado": _num(form.valor_dotado.data),
                },
                commit=False,
            )
            db.session.flush()
            registrar("publico.dotacao_criar", entidade="dotacao", entidade_id=dot.id)
            db.session.commit()
            flash("Dotação cadastrada.", "success")
            return redirect(url_for("publico.dotacoes"))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("publico/dotacao_form.html", form=form, titulo="Nova dotação")


# --------------------------------------------------------------------------- #
# Processos de contratação
# --------------------------------------------------------------------------- #
@bp.route("/processos")
@login_required
@requer_permissao("licitacao.gerenciar")
def processos():
    status = request.args.get("status")
    modalidade = request.args.get("modalidade")
    pagina = request.args.get("page", 1, type=int)
    stmt = select(ProcessoContratacao).where(ProcessoContratacao.organizacao_id == _org_id())
    if status in STATUS_PROCESSO:
        stmt = stmt.where(ProcessoContratacao.status == status)
    if modalidade in MODALIDADES:
        stmt = stmt.where(ProcessoContratacao.modalidade == modalidade)
    stmt = stmt.order_by(ProcessoContratacao.numero_processo.desc())
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template(
        "publico/processos.html",
        paginacao=paginacao,
        status=status,
        modalidade=modalidade,
        status_opcoes=STATUS_PROCESSO_CHOICES,
        modalidade_opcoes=[(m, ROTULO_MODALIDADE[m]) for m in MODALIDADES],
    )


@bp.route("/processos/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("licitacao.gerenciar")
def processo_novo():
    form = ProcessoForm()
    form.setor_id.choices = _choices_setores()
    if form.validate_on_submit():
        try:
            proc = publico_service.criar_processo(
                _org_id(),
                dados={
                    "numero_processo": form.numero_processo.data,
                    "objeto": form.objeto.data,
                    "modalidade": form.modalidade.data,
                    "procedimento_auxiliar": form.procedimento_auxiliar.data,
                    "valor_estimado": _num(form.valor_estimado.data),
                    "setor_id": form.setor_id.data or None,
                    "data_abertura": form.data_abertura.data,
                    "numero_pncp": form.numero_pncp.data or None,
                    "observacoes": form.observacoes.data or None,
                },
                commit=False,
            )
            db.session.flush()
            registrar("publico.processo_criar", entidade="processo", entidade_id=proc.id)
            db.session.commit()
            flash("Processo cadastrado.", "success")
            return redirect(url_for("publico.processo_detalhe", processo_id=proc.id))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("publico/processo_form.html", form=form, titulo="Novo processo")


@bp.route("/processos/<int:processo_id>")
@login_required
@requer_permissao("licitacao.gerenciar")
def processo_detalhe(processo_id: int):
    processo = _ou_404(ProcessoContratacao, processo_id)
    return render_template(
        "publico/processo_detalhe.html",
        processo=processo,
        status_opcoes=STATUS_PROCESSO_CHOICES,
    )


@bp.route("/processos/<int:processo_id>/status", methods=["POST"])
@login_required
@requer_permissao("licitacao.gerenciar")
def processo_status(processo_id: int):
    processo = _ou_404(ProcessoContratacao, processo_id)
    try:
        publico_service.definir_status_processo(
            processo, request.form.get("status", ""), commit=False
        )
        registrar("publico.processo_status", entidade="processo", entidade_id=processo.id)
        db.session.commit()
        flash("Status do processo atualizado.", "success")
    except ErroPublico as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("publico.processo_detalhe", processo_id=processo.id))


# --------------------------------------------------------------------------- #
# Atas de registro de preços
# --------------------------------------------------------------------------- #
@bp.route("/atas")
@login_required
@requer_permissao("ata.gerenciar")
def atas():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(AtaRegistroPrecos)
        .where(AtaRegistroPrecos.organizacao_id == _org_id())
        .order_by(AtaRegistroPrecos.numero.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("publico/atas.html", paginacao=paginacao)


@bp.route("/atas/nova", methods=["GET", "POST"])
@login_required
@requer_permissao("ata.gerenciar")
def ata_nova():
    form = AtaForm()
    form.fornecedor_id.choices = _choices_fornecedores(opcional=False)
    form.processo_id.choices = _choices_processos()
    if form.validate_on_submit():
        try:
            ata = publico_service.criar_ata(
                _org_id(),
                dados={
                    "numero": form.numero.data,
                    "fornecedor_id": form.fornecedor_id.data,
                    "processo_id": form.processo_id.data or None,
                    "vigencia_inicio": form.vigencia_inicio.data,
                    "vigencia_fim": form.vigencia_fim.data,
                    "observacoes": form.observacoes.data or None,
                },
                itens=_parse_itens(),
                commit=False,
            )
            db.session.flush()
            registrar("publico.ata_criar", entidade="ata", entidade_id=ata.id)
            db.session.commit()
            flash(f"Ata {ata.numero} cadastrada.", "success")
            return redirect(url_for("publico.ata_detalhe", ata_id=ata.id))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "publico/ata_form.html",
        form=form,
        titulo="Nova ata",
        produtos=_choices_produtos(),
        itens=[],
    )


@bp.route("/atas/<int:ata_id>")
@login_required
@requer_permissao("ata.gerenciar")
def ata_detalhe(ata_id: int):
    ata = _ou_404(AtaRegistroPrecos, ata_id)
    return render_template("publico/ata_detalhe.html", ata=ata)


# --------------------------------------------------------------------------- #
# Contratos e aditivos
# --------------------------------------------------------------------------- #
@bp.route("/contratos")
@login_required
@requer_permissao("contrato.gerenciar")
def contratos():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(Contrato)
        .where(Contrato.organizacao_id == _org_id())
        .order_by(Contrato.numero.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("publico/contratos.html", paginacao=paginacao)


@bp.route("/contratos/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("contrato.gerenciar")
def contrato_novo():
    form = ContratoForm()
    form.fornecedor_id.choices = _choices_fornecedores(opcional=False)
    form.processo_id.choices = _choices_processos()
    form.ata_id.choices = _choices_atas()
    form.fiscal_id.choices = _choices_usuarios()
    form.gestor_id.choices = _choices_usuarios()
    if form.validate_on_submit():
        try:
            contrato = publico_service.criar_contrato(
                _org_id(),
                dados={
                    "numero": form.numero.data,
                    "objeto": form.objeto.data,
                    "fornecedor_id": form.fornecedor_id.data,
                    "processo_id": form.processo_id.data or None,
                    "ata_id": form.ata_id.data or None,
                    "vigencia_inicio": form.vigencia_inicio.data,
                    "vigencia_fim": form.vigencia_fim.data,
                    "fiscal_id": form.fiscal_id.data or None,
                    "gestor_id": form.gestor_id.data or None,
                    "garantia": form.garantia.data or None,
                    "observacoes": form.observacoes.data or None,
                },
                itens=_parse_itens(),
                commit=False,
            )
            db.session.flush()
            registrar("publico.contrato_criar", entidade="contrato", entidade_id=contrato.id)
            db.session.commit()
            flash(f"Contrato {contrato.numero} cadastrado.", "success")
            return redirect(url_for("publico.contrato_detalhe", contrato_id=contrato.id))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template(
        "publico/contrato_form.html",
        form=form,
        titulo="Novo contrato",
        produtos=_choices_produtos(),
        itens=[],
    )


@bp.route("/contratos/<int:contrato_id>")
@login_required
@requer_permissao("contrato.gerenciar")
def contrato_detalhe(contrato_id: int):
    contrato = _ou_404(Contrato, contrato_id)
    return render_template(
        "publico/contrato_detalhe.html", contrato=contrato, aditivo_form=AditivoForm()
    )


@bp.route("/contratos/<int:contrato_id>/aditivo", methods=["POST"])
@login_required
@requer_permissao("contrato.gerenciar")
def contrato_aditivo(contrato_id: int):
    contrato = _ou_404(Contrato, contrato_id)
    form = AditivoForm()
    if form.validate_on_submit():
        try:
            publico_service.adicionar_aditivo(
                contrato,
                dados={
                    "tipo": form.tipo.data,
                    "numero": form.numero.data or None,
                    "valor": _num(form.valor.data),
                    "nova_vigencia": form.nova_vigencia.data,
                    "descricao": form.descricao.data or None,
                },
                commit=False,
            )
            registrar("publico.contrato_aditivo", entidade="contrato", entidade_id=contrato.id)
            db.session.commit()
            flash("Aditivo registrado.", "success")
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    else:
        flash("Verifique os dados do aditivo.", "danger")
    return redirect(url_for("publico.contrato_detalhe", contrato_id=contrato.id))


# --------------------------------------------------------------------------- #
# Empenhos
# --------------------------------------------------------------------------- #
@bp.route("/empenhos")
@login_required
@requer_permissao("empenho.emitir")
def empenhos():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(Empenho).where(Empenho.organizacao_id == _org_id()).order_by(Empenho.numero.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("publico/empenhos.html", paginacao=paginacao)


@bp.route("/empenhos/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("empenho.emitir")
def empenho_novo():
    form = EmpenhoForm()
    form.dotacao_id.choices = _choices_dotacoes()
    form.contrato_id.choices = _choices_contratos()
    form.ata_id.choices = _choices_atas()
    form.processo_id.choices = _choices_processos()
    form.fornecedor_id.choices = _choices_fornecedores()
    if form.validate_on_submit():
        try:
            empenho = publico_service.emitir_empenho(
                _org_id(),
                numero=form.numero.data or None,
                tipo=form.tipo.data,
                valor=_num(form.valor.data),
                dotacao_id=form.dotacao_id.data,
                contrato_id=form.contrato_id.data or None,
                ata_id=form.ata_id.data or None,
                processo_id=form.processo_id.data or None,
                fornecedor_id=form.fornecedor_id.data or None,
                data=form.data.data,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            db.session.flush()
            registrar("publico.empenho_emitir", entidade="empenho", entidade_id=empenho.id)
            db.session.commit()
            flash(f"Empenho {empenho.numero} emitido.", "success")
            return redirect(url_for("publico.empenho_detalhe", empenho_id=empenho.id))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("publico/empenho_form.html", form=form, titulo="Novo empenho")


@bp.route("/empenhos/<int:empenho_id>")
@login_required
@requer_permissao("empenho.emitir")
def empenho_detalhe(empenho_id: int):
    empenho = _ou_404(Empenho, empenho_id)
    liquidacoes = db.session.scalars(
        select(Liquidacao)
        .where(Liquidacao.empenho_id == empenho.id)
        .order_by(Liquidacao.id.desc())
    ).all()
    liq_form = LiquidacaoForm()
    liq_form.nota_fiscal_id.choices = _choices_notas()
    liq_form.recebimento_id.choices = _choices_recebimentos_definitivos()
    return render_template(
        "publico/empenho_detalhe.html",
        empenho=empenho,
        liquidacoes=liquidacoes,
        liq_form=liq_form,
    )


@bp.route("/empenhos/<int:empenho_id>/anular", methods=["POST"])
@login_required
@requer_permissao("empenho.emitir")
def empenho_anular(empenho_id: int):
    empenho = _ou_404(Empenho, empenho_id)
    try:
        publico_service.anular_empenho(empenho, commit=False)
        registrar("publico.empenho_anular", entidade="empenho", entidade_id=empenho.id)
        db.session.commit()
        flash("Empenho anulado e saldos restaurados.", "success")
    except ErroPublico as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("publico.empenho_detalhe", empenho_id=empenho.id))


@bp.route("/empenhos/<int:empenho_id>/liquidar", methods=["POST"])
@login_required
@requer_permissao("despesa.liquidar")
def empenho_liquidar(empenho_id: int):
    empenho = _ou_404(Empenho, empenho_id)
    form = LiquidacaoForm()
    form.nota_fiscal_id.choices = _choices_notas()
    form.recebimento_id.choices = _choices_recebimentos_definitivos()
    if form.validate_on_submit():
        try:
            liq = publico_service.liquidar(
                _org_id(),
                empenho_id=empenho.id,
                valor=_num(form.valor.data),
                nota_fiscal_id=form.nota_fiscal_id.data or None,
                recebimento_id=form.recebimento_id.data or None,
                atestado_por_id=current_user.id,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            db.session.flush()
            registrar("publico.liquidar", entidade="liquidacao", entidade_id=liq.id)
            db.session.commit()
            flash("Liquidação registrada.", "success")
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    else:
        flash("Verifique os dados da liquidação.", "danger")
    return redirect(url_for("publico.empenho_detalhe", empenho_id=empenho.id))


# --------------------------------------------------------------------------- #
# Recebimentos
# --------------------------------------------------------------------------- #
@bp.route("/recebimentos")
@login_required
@requer_permissao("recebimento.definitivo")
def recebimentos():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(Recebimento)
        .where(Recebimento.organizacao_id == _org_id())
        .order_by(Recebimento.id.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template("publico/recebimentos.html", paginacao=paginacao)


@bp.route("/recebimentos/novo", methods=["GET", "POST"])
@login_required
@requer_permissao("recebimento.definitivo")
def recebimento_novo():
    form = RecebimentoForm()
    form.nota_fiscal_id.choices = _choices_notas()
    form.empenho_id.choices = _choices_empenhos()
    form.contrato_id.choices = _choices_contratos()
    form.setor_id.choices = _choices_setores()
    if form.validate_on_submit():
        try:
            receb = publico_service.registrar_recebimento(
                _org_id(),
                tipo=form.tipo.data,
                nota_fiscal_id=form.nota_fiscal_id.data or None,
                empenho_id=form.empenho_id.data or None,
                contrato_id=form.contrato_id.data or None,
                setor_id=form.setor_id.data or None,
                data=form.data.data,
                conforme=form.conforme.data,
                recebido_por_id=current_user.id,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            db.session.flush()
            registrar("publico.recebimento", entidade="recebimento", entidade_id=receb.id)
            db.session.commit()
            flash("Recebimento registrado.", "success")
            return redirect(url_for("publico.recebimentos"))
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return render_template("publico/recebimento_form.html", form=form, titulo="Novo recebimento")


# --------------------------------------------------------------------------- #
# Liquidações e pagamentos
# --------------------------------------------------------------------------- #
@bp.route("/liquidacoes")
@login_required
@requer_permissao("despesa.liquidar", "despesa.pagar")
def liquidacoes():
    pagina = request.args.get("page", 1, type=int)
    stmt = (
        select(Liquidacao)
        .where(Liquidacao.organizacao_id == _org_id())
        .order_by(Liquidacao.id.desc())
    )
    paginacao = db.paginate(stmt, page=pagina, per_page=25, error_out=False)
    return render_template(
        "publico/liquidacoes.html", paginacao=paginacao, pagamento_form=PagamentoForm()
    )


@bp.route("/liquidacoes/<int:liquidacao_id>/pagar", methods=["POST"])
@login_required
@requer_permissao("despesa.pagar")
def liquidacao_pagar(liquidacao_id: int):
    liquidacao = _ou_404(Liquidacao, liquidacao_id)
    form = PagamentoForm()
    if form.validate_on_submit():
        try:
            pag = publico_service.pagar(
                _org_id(),
                liquidacao_id=liquidacao.id,
                valor=_num(form.valor.data),
                ordem_bancaria=form.ordem_bancaria.data or None,
                data=form.data.data,
                observacoes=form.observacoes.data or None,
                commit=False,
            )
            db.session.flush()
            registrar("publico.pagar", entidade="pagamento", entidade_id=pag.id)
            db.session.commit()
            flash("Pagamento registrado.", "success")
        except ErroPublico as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    else:
        flash("Informe um valor de pagamento válido.", "danger")
    return redirect(url_for("publico.liquidacoes"))
