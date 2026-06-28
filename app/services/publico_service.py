"""Serviço de compras públicas (§7.10) — cadeia da despesa com saldos consistentes.

Regras de ouro (Lei 14.133/2021):
- **Empenho** reserva recurso: nunca acima do ``saldo_disponivel`` da dotação; quando
  vinculado a contrato/ata, consome o saldo desses (nada fica negativo).
- **Liquidação** baixa o ``saldo_a_liquidar`` do empenho (exige NF + recebimento
  definitivo + atesto); **pagamento** baixa o saldo da liquidação.
- **Recebimento definitivo** é o gatilho da **entrada valorada** no almoxarifado.
- Toda baixa de saldo é validada antes de gravar; anulações restauram os saldos.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.compras import NF_LANCADA, NotaFiscal
from app.models.publico import (
    EMP_ANULADO,
    EMP_EMITIDO,
    EMP_LIQUIDADO,
    EMP_PARC_LIQUIDADO,
    LIQ_PAGA,
    LIQ_REGISTRADA,
    RECEB_DEFINITIVO,
    STATUS_PROCESSO,
    AtaItem,
    AtaRegistroPrecos,
    Contrato,
    ContratoItem,
    DotacaoOrcamentaria,
    Empenho,
    Liquidacao,
    Pagamento,
    ProcessoContratacao,
    Recebimento,
)
from app.services import compra_service


class ErroPublico(Exception):
    """Erro de regra de negócio nas compras públicas."""


def _dec(valor: Any) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _q2(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"))


def _por_id(modelo, organizacao_id: int, ident: int | None, rotulo: str):
    if ident is None:
        return None
    obj = db.session.get(modelo, ident)
    if obj is None or obj.organizacao_id != organizacao_id:
        raise ErroPublico(f"{rotulo} inválido para esta organização.")
    return obj


# ===================================================== Dotação orçamentária === #
def criar_dotacao(organizacao_id: int, *, dados: dict[str, Any], commit: bool = True):
    dotacao = DotacaoOrcamentaria(
        organizacao_id=organizacao_id,
        valor_dotado=_dec(dados.get("valor_dotado")),
        valor_empenhado=Decimal(0),
        exercicio=dados.get("exercicio") or date.today().year,
        programa_trabalho=dados.get("programa_trabalho"),
        natureza_despesa=dados.get("natureza_despesa"),
        fonte_recurso=dados.get("fonte_recurso"),
        unidade_orcamentaria=dados.get("unidade_orcamentaria"),
        descricao=dados.get("descricao"),
    )
    db.session.add(dotacao)
    if commit:
        db.session.commit()
    return dotacao


# ==================================================== Processo de contratação === #
def criar_processo(organizacao_id: int, *, dados: dict[str, Any], commit: bool = True):
    processo = ProcessoContratacao(
        organizacao_id=organizacao_id,
        numero_processo=(dados["numero_processo"]).strip(),
        objeto=(dados.get("objeto") or "").strip(),
        modalidade=dados["modalidade"],
        procedimento_auxiliar=dados.get("procedimento_auxiliar") or "NENHUM",
        valor_estimado=_dec(dados.get("valor_estimado")),
        setor_id=dados.get("setor_id"),
        data_abertura=dados.get("data_abertura"),
        numero_pncp=dados.get("numero_pncp"),
        observacoes=dados.get("observacoes"),
    )
    db.session.add(processo)
    if commit:
        db.session.commit()
    return processo


def definir_status_processo(processo: ProcessoContratacao, status: str, *, commit: bool = True):
    if status not in STATUS_PROCESSO:
        raise ErroPublico("Status de processo inválido.")
    processo.status = status
    if status == "HOMOLOGADO" and processo.data_homologacao is None:
        processo.data_homologacao = date.today()
    if commit:
        db.session.commit()
    return processo


# ============================================================= Ata de SRP === #
def criar_ata(
    organizacao_id: int, *, dados: dict[str, Any], itens: list[dict], commit: bool = True
):
    _por_id(ProcessoContratacao, organizacao_id, dados.get("processo_id"), "Processo")
    fornecedor = compra_service._validar_fornecedor(organizacao_id, dados.get("fornecedor_id"))
    if fornecedor is None:
        raise ErroPublico("A ata exige um fornecedor.")
    ata = AtaRegistroPrecos(
        organizacao_id=organizacao_id,
        numero=(dados["numero"]).strip(),
        processo_id=dados.get("processo_id"),
        fornecedor_id=dados["fornecedor_id"],
        vigencia_inicio=dados.get("vigencia_inicio"),
        vigencia_fim=dados.get("vigencia_fim"),
        observacoes=dados.get("observacoes"),
    )
    ata.itens = [_ata_item(organizacao_id, linha) for linha in _linhas_validas(itens)]
    db.session.add(ata)
    if commit:
        db.session.commit()
    return ata


def _ata_item(organizacao_id: int, linha: dict) -> AtaItem:
    qtd = _dec(linha.get("quantidade"))
    return AtaItem(
        organizacao_id=organizacao_id,
        produto_id=linha.get("produto_id") or None,
        descricao=linha["descricao"],
        quantidade_registrada=qtd,
        preco_registrado=_dec(linha.get("valor_unitario")),
        saldo_quantidade=qtd,
    )


def _saldo_valor_ata(ata: AtaRegistroPrecos) -> Decimal:
    return _q2(
        sum((_dec(i.saldo_quantidade) * _dec(i.preco_registrado) for i in ata.itens), Decimal(0))
    )


# ============================================================== Contrato === #
def criar_contrato(
    organizacao_id: int, *, dados: dict[str, Any], itens: list[dict], commit: bool = True
):
    _por_id(ProcessoContratacao, organizacao_id, dados.get("processo_id"), "Processo")
    _por_id(AtaRegistroPrecos, organizacao_id, dados.get("ata_id"), "Ata")
    if compra_service._validar_fornecedor(organizacao_id, dados.get("fornecedor_id")) is None:
        raise ErroPublico("O contrato exige um fornecedor.")

    linhas = _linhas_validas(itens)
    contrato = Contrato(
        organizacao_id=organizacao_id,
        numero=(dados["numero"]).strip(),
        objeto=(dados.get("objeto") or "").strip(),
        processo_id=dados.get("processo_id"),
        ata_id=dados.get("ata_id"),
        fornecedor_id=dados["fornecedor_id"],
        vigencia_inicio=dados.get("vigencia_inicio"),
        vigencia_fim=dados.get("vigencia_fim"),
        fiscal_id=dados.get("fiscal_id"),
        gestor_id=dados.get("gestor_id"),
        garantia=dados.get("garantia"),
        observacoes=dados.get("observacoes"),
    )
    contrato.itens = [_contrato_item(organizacao_id, linha) for linha in linhas]
    contrato.valor_global = _q2(sum((_dec(i.saldo_valor) for i in contrato.itens), Decimal(0)))
    db.session.add(contrato)
    if commit:
        db.session.commit()
    return contrato


def _contrato_item(organizacao_id: int, linha: dict) -> ContratoItem:
    qtd = _dec(linha.get("quantidade"))
    preco = _dec(linha.get("valor_unitario"))
    return ContratoItem(
        organizacao_id=organizacao_id,
        produto_id=linha.get("produto_id") or None,
        descricao=linha["descricao"],
        quantidade=qtd,
        preco_unitario=preco,
        saldo_quantidade=qtd,
        saldo_valor=_q2(qtd * preco),
    )


def _saldo_valor_contrato(contrato: Contrato) -> Decimal:
    return _q2(sum((_dec(i.saldo_valor) for i in contrato.itens), Decimal(0)))


def adicionar_aditivo(contrato: Contrato, *, dados: dict[str, Any], commit: bool = True):
    from app.models.publico import ADITIVO_PRAZO, ADITIVO_VALOR, TIPOS_ADITIVO, TermoAditivo

    tipo = dados["tipo"]
    if tipo not in TIPOS_ADITIVO:
        raise ErroPublico("Tipo de aditivo inválido.")
    aditivo = TermoAditivo(
        organizacao_id=contrato.organizacao_id,
        contrato_id=contrato.id,
        numero=dados.get("numero"),
        tipo=tipo,
        descricao=dados.get("descricao"),
        valor=_dec(dados.get("valor")) if dados.get("valor") else None,
        nova_vigencia=dados.get("nova_vigencia"),
    )
    db.session.add(aditivo)
    # Aditivo de valor aumenta o valor global e o saldo do primeiro item (acréscimo).
    if tipo == ADITIVO_VALOR and aditivo.valor:
        contrato.valor_global = _q2(_dec(contrato.valor_global) + aditivo.valor)
        if contrato.itens:
            it = contrato.itens[0]
            it.saldo_valor = _q2(_dec(it.saldo_valor) + aditivo.valor)
    if tipo == ADITIVO_PRAZO and aditivo.nova_vigencia:
        contrato.vigencia_fim = aditivo.nova_vigencia
    if commit:
        db.session.commit()
    return aditivo


# =============================================================== Empenho === #
def proximo_numero_empenho(organizacao_id: int) -> int:
    maximo = db.session.scalar(
        select(func.count(Empenho.id)).where(Empenho.organizacao_id == organizacao_id)
    )
    return int(maximo or 0) + 1


def _consumir_saldo_contrato(contrato: Contrato, valor: Decimal) -> None:
    disponivel = _saldo_valor_contrato(contrato)
    if valor > disponivel:
        raise ErroPublico(
            f"Empenho excede o saldo do contrato (disponível R$ {disponivel}, empenho R$ {valor})."
        )
    restante = valor
    for item in contrato.itens:
        if restante <= 0:
            break
        usar = min(_dec(item.saldo_valor), restante)
        if usar <= 0:
            continue
        preco = _dec(item.preco_unitario)
        item.saldo_valor = _q2(_dec(item.saldo_valor) - usar)
        if preco > 0:
            item.saldo_quantidade = _dec(item.saldo_quantidade) - (usar / preco)
        restante -= usar


def _restaurar_saldo_contrato(contrato: Contrato, valor: Decimal) -> None:
    restante = valor
    for item in contrato.itens:
        if restante <= 0:
            break
        capacidade = _q2(_dec(item.quantidade) * _dec(item.preco_unitario)) - _dec(item.saldo_valor)
        repor = min(capacidade, restante)
        if repor <= 0:
            continue
        preco = _dec(item.preco_unitario)
        item.saldo_valor = _q2(_dec(item.saldo_valor) + repor)
        if preco > 0:
            item.saldo_quantidade = _dec(item.saldo_quantidade) + (repor / preco)
        restante -= repor


def _consumir_saldo_ata(ata: AtaRegistroPrecos, valor: Decimal) -> None:
    disponivel = _saldo_valor_ata(ata)
    if valor > disponivel:
        raise ErroPublico(
            f"Empenho excede o saldo da ata (disponível R$ {disponivel}, empenho R$ {valor})."
        )
    restante = valor
    for item in ata.itens:
        if restante <= 0:
            break
        preco = _dec(item.preco_registrado)
        saldo_item = _q2(_dec(item.saldo_quantidade) * preco)
        usar = min(saldo_item, restante)
        if usar <= 0 or preco <= 0:
            continue
        item.saldo_quantidade = _dec(item.saldo_quantidade) - (usar / preco)
        restante -= usar


def emitir_empenho(
    organizacao_id: int,
    *,
    numero: str | None = None,
    tipo: str = "ORDINARIO",
    valor: Any,
    dotacao_id: int,
    contrato_id: int | None = None,
    ata_id: int | None = None,
    processo_id: int | None = None,
    fornecedor_id: int | None = None,
    data: date | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Empenho:
    valor = _q2(_dec(valor))
    if valor <= 0:
        raise ErroPublico("O valor do empenho deve ser maior que zero.")

    dotacao = _por_id(DotacaoOrcamentaria, organizacao_id, dotacao_id, "Dotação")
    if dotacao is None:
        raise ErroPublico("Informe a dotação orçamentária.")
    if valor > dotacao.saldo_disponivel:
        raise ErroPublico(
            f"Empenho excede o saldo da dotação "
            f"(disponível R$ {dotacao.saldo_disponivel}, empenho R$ {valor})."
        )

    contrato = _por_id(Contrato, organizacao_id, contrato_id, "Contrato")
    ata = _por_id(AtaRegistroPrecos, organizacao_id, ata_id, "Ata")
    _por_id(ProcessoContratacao, organizacao_id, processo_id, "Processo")
    compra_service._validar_fornecedor(organizacao_id, fornecedor_id)

    if contrato is not None:
        _consumir_saldo_contrato(contrato, valor)
    if ata is not None:
        _consumir_saldo_ata(ata, valor)

    dotacao.valor_empenhado = _q2(_dec(dotacao.valor_empenhado) + valor)

    empenho = Empenho(
        organizacao_id=organizacao_id,
        numero=(numero or "").strip() or str(proximo_numero_empenho(organizacao_id)),
        tipo=tipo,
        data=data or date.today(),
        valor=valor,
        saldo_a_liquidar=valor,
        dotacao_id=dotacao_id,
        contrato_id=contrato_id,
        ata_id=ata_id,
        processo_id=processo_id,
        fornecedor_id=fornecedor_id,
        observacoes=observacoes,
        status=EMP_EMITIDO,
    )
    db.session.add(empenho)
    if commit:
        db.session.commit()
    return empenho


def anular_empenho(empenho: Empenho, *, commit: bool = True) -> Empenho:
    if empenho.status == EMP_ANULADO:
        raise ErroPublico("Empenho já anulado.")
    if empenho.valor_liquidado > 0:
        raise ErroPublico("Não é possível anular um empenho já liquidado (total ou parcial).")

    empenho.dotacao.valor_empenhado = _q2(
        _dec(empenho.dotacao.valor_empenhado) - _dec(empenho.valor)
    )
    if empenho.contrato is not None:
        _restaurar_saldo_contrato(empenho.contrato, _dec(empenho.valor))
    empenho.saldo_a_liquidar = Decimal(0)
    empenho.status = EMP_ANULADO
    if commit:
        db.session.commit()
    return empenho


# ============================================================ Recebimento === #
def registrar_recebimento(
    organizacao_id: int,
    *,
    tipo: str,
    nota_fiscal_id: int | None = None,
    empenho_id: int | None = None,
    contrato_id: int | None = None,
    setor_id: int | None = None,
    data: date | None = None,
    conforme: bool = True,
    recebido_por_id: int | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Recebimento:
    nota = _por_id(NotaFiscal, organizacao_id, nota_fiscal_id, "Nota fiscal")
    _por_id(Empenho, organizacao_id, empenho_id, "Empenho")
    _por_id(Contrato, organizacao_id, contrato_id, "Contrato")

    recebimento = Recebimento(
        organizacao_id=organizacao_id,
        tipo=tipo,
        nota_fiscal_id=nota_fiscal_id,
        empenho_id=empenho_id,
        contrato_id=contrato_id,
        setor_id=setor_id,
        data=data or date.today(),
        conforme=conforme,
        recebido_por_id=recebido_por_id,
        observacoes=observacoes,
    )
    db.session.add(recebimento)

    # Recebimento definitivo conforme dispara a entrada valorada (art. 140).
    if tipo == RECEB_DEFINITIVO and conforme and nota is not None and nota.status != NF_LANCADA:
        compra_service.lancar_entrada_valorada(
            nota, usuario_id=recebido_por_id, commit=False
        )
    if commit:
        db.session.commit()
    return recebimento


# ====================================================== Liquidação e pagamento === #
def liquidar(
    organizacao_id: int,
    *,
    empenho_id: int,
    valor: Any,
    nota_fiscal_id: int | None = None,
    recebimento_id: int | None = None,
    atestado_por_id: int | None = None,
    data: date | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Liquidacao:
    empenho = _por_id(Empenho, organizacao_id, empenho_id, "Empenho")
    if empenho is None:
        raise ErroPublico("Informe o empenho.")
    if empenho.status == EMP_ANULADO:
        raise ErroPublico("Empenho anulado não pode ser liquidado.")
    valor = _q2(_dec(valor))
    if valor <= 0:
        raise ErroPublico("O valor da liquidação deve ser maior que zero.")
    if valor > _dec(empenho.saldo_a_liquidar):
        raise ErroPublico(
            f"Liquidação excede o saldo a liquidar do empenho "
            f"(disponível R$ {empenho.saldo_a_liquidar}, liquidação R$ {valor})."
        )

    recebimento = _por_id(Recebimento, organizacao_id, recebimento_id, "Recebimento")
    if recebimento is not None and not recebimento.is_definitivo:
        raise ErroPublico("A liquidação exige um recebimento definitivo.")
    _por_id(NotaFiscal, organizacao_id, nota_fiscal_id, "Nota fiscal")

    empenho.saldo_a_liquidar = _q2(_dec(empenho.saldo_a_liquidar) - valor)
    empenho.status = EMP_LIQUIDADO if empenho.saldo_a_liquidar <= 0 else EMP_PARC_LIQUIDADO

    liquidacao = Liquidacao(
        organizacao_id=organizacao_id,
        empenho_id=empenho_id,
        nota_fiscal_id=nota_fiscal_id,
        recebimento_id=recebimento_id,
        valor=valor,
        data=data or date.today(),
        atestado_por_id=atestado_por_id,
        status=LIQ_REGISTRADA,
        observacoes=observacoes,
    )
    db.session.add(liquidacao)
    if commit:
        db.session.commit()
    return liquidacao


def pagar(
    organizacao_id: int,
    *,
    liquidacao_id: int,
    valor: Any,
    ordem_bancaria: str | None = None,
    data: date | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Pagamento:
    liquidacao = _por_id(Liquidacao, organizacao_id, liquidacao_id, "Liquidação")
    if liquidacao is None:
        raise ErroPublico("Informe a liquidação.")
    valor = _q2(_dec(valor))
    if valor <= 0:
        raise ErroPublico("O valor do pagamento deve ser maior que zero.")
    saldo = _dec(liquidacao.valor) - liquidacao.valor_pago
    if valor > saldo:
        raise ErroPublico(
            f"Pagamento excede o saldo da liquidação "
            f"(disponível R$ {_q2(saldo)}, pagamento R$ {valor})."
        )

    pagamento = Pagamento(
        organizacao_id=organizacao_id,
        liquidacao=liquidacao,
        valor=valor,
        data=data or date.today(),
        ordem_bancaria=ordem_bancaria,
        observacoes=observacoes,
    )
    db.session.add(pagamento)
    db.session.flush()
    # `saldo` já reflete o total pago anterior; somar o valor atual evita depender
    # do refresh da coleção `pagamentos` (que pode estar stale após o flush).
    if valor >= saldo:
        liquidacao.status = LIQ_PAGA
    if commit:
        db.session.commit()
    return pagamento


# ---------------------------------------------------------------- Helpers --- #
def _linhas_validas(itens: list[dict]) -> list[dict]:
    limpos = []
    for item in itens or []:
        descricao = (item.get("descricao") or "").strip()
        produto_id = item.get("produto_id") or None
        if not descricao and not produto_id:
            continue
        if _dec(item.get("quantidade")) <= 0:
            raise ErroPublico(f"Quantidade inválida no item {descricao or produto_id!r}.")
        limpos.append({**item, "descricao": descricao or "(produto)"})
    if not limpos:
        raise ErroPublico("Informe ao menos um item.")
    return limpos
