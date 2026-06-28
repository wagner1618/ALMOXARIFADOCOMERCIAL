"""Testes do serviço de compras públicas: cadeia da despesa e consistência de saldos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.compras import NF_LANCADA
from app.models.publico import (
    EMP_ANULADO,
    EMP_LIQUIDADO,
    EMP_PARC_LIQUIDADO,
    LIQ_PAGA,
    PREGAO,
    RECEB_DEFINITIVO,
    RECEB_PROVISORIO,
)
from app.models.setor import Setor
from app.services import compra_service, estoque_service, produto_service, publico_service, setup
from app.services.publico_service import ErroPublico


def _item(descricao, quantidade, valor, produto_id=None):
    return {
        "produto_id": produto_id,
        "descricao": descricao,
        "quantidade": quantidade,
        "valor_unitario": valor,
    }


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org Publica", slug="publica")
    org.config = {**org.config, "modo_compra": "PUBLICO"}
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    setor.poder_compra = True
    prod = produto_service.criar_produto(org.id, nome="Papel A4", unidade="RESMA", commit=False)
    forn = compra_service.criar_fornecedor(
        org.id, dados={"nome": "Fornecedor Y", "documento": "333"}, commit=False
    )
    db.session.commit()
    dot = publico_service.criar_dotacao(
        org.id, dados={"descricao": "Material de consumo", "valor_dotado": "10000"}
    )
    return {"org": org, "setor": setor, "prod": prod, "forn": forn, "dot": dot}


# ----------------------------------------------------------------- Dotação --- #
def test_dotacao_saldo_disponivel(cenario):
    assert cenario["dot"].saldo_disponivel == Decimal("10000.00")


def test_empenho_dentro_do_saldo_decrementa_dotacao(cenario):
    c = cenario
    emp = publico_service.emitir_empenho(
        c["org"].id, valor="3000", dotacao_id=c["dot"].id, fornecedor_id=c["forn"].id
    )
    db.session.refresh(c["dot"])
    assert c["dot"].valor_empenhado == Decimal("3000.00")
    assert c["dot"].saldo_disponivel == Decimal("7000.00")
    assert emp.saldo_a_liquidar == Decimal("3000.00")


def test_empenho_acima_do_saldo_da_dotacao_bloqueia(cenario):
    c = cenario
    with pytest.raises(ErroPublico, match="saldo da dotação"):
        publico_service.emitir_empenho(c["org"].id, valor="20000", dotacao_id=c["dot"].id)


# ---------------------------------------------------------------- Contrato --- #
def _contrato(cenario, qtd="100", preco="10"):
    c = cenario
    return publico_service.criar_contrato(
        c["org"].id,
        dados={"numero": "CT-1", "objeto": "Papel", "fornecedor_id": c["forn"].id},
        itens=[_item("Papel", qtd, preco, c["prod"].id)],
    )


def test_contrato_calcula_valor_global_e_saldo(cenario):
    contrato = _contrato(cenario, "100", "10")
    assert contrato.valor_global == Decimal("1000.00")
    assert contrato.itens[0].saldo_valor == Decimal("1000.00")


def test_empenho_consome_saldo_do_contrato(cenario):
    c = cenario
    contrato = _contrato(cenario, "100", "10")
    publico_service.emitir_empenho(
        c["org"].id, valor="400", dotacao_id=c["dot"].id, contrato_id=contrato.id
    )
    db.session.refresh(contrato)
    assert publico_service._saldo_valor_contrato(contrato) == Decimal("600.00")


def test_empenho_acima_do_saldo_do_contrato_bloqueia(cenario):
    c = cenario
    contrato = _contrato(cenario, "100", "10")
    with pytest.raises(ErroPublico, match="saldo do contrato"):
        publico_service.emitir_empenho(
            c["org"].id, valor="1500", dotacao_id=c["dot"].id, contrato_id=contrato.id
        )


def test_anular_empenho_restaura_dotacao_e_contrato(cenario):
    c = cenario
    contrato = _contrato(cenario, "100", "10")
    emp = publico_service.emitir_empenho(
        c["org"].id, valor="400", dotacao_id=c["dot"].id, contrato_id=contrato.id
    )
    publico_service.anular_empenho(emp)
    db.session.refresh(c["dot"])
    db.session.refresh(contrato)
    assert emp.status == EMP_ANULADO
    assert c["dot"].valor_empenhado == Decimal("0.00")
    assert publico_service._saldo_valor_contrato(contrato) == Decimal("1000.00")


# --------------------------------------------------------------------- Ata --- #
def test_empenho_consome_saldo_da_ata(cenario):
    c = cenario
    processo = publico_service.criar_processo(
        c["org"].id,
        dados={"numero_processo": "PR-1", "objeto": "SRP", "modalidade": PREGAO},
    )
    ata = publico_service.criar_ata(
        c["org"].id,
        dados={"numero": "ATA-1", "processo_id": processo.id, "fornecedor_id": c["forn"].id},
        itens=[_item("Papel", "200", "5", c["prod"].id)],
    )
    assert publico_service._saldo_valor_ata(ata) == Decimal("1000.00")
    publico_service.emitir_empenho(
        c["org"].id, valor="500", dotacao_id=c["dot"].id, ata_id=ata.id
    )
    db.session.refresh(ata)
    assert publico_service._saldo_valor_ata(ata) == Decimal("500.00")


# -------------------------------------------------- Recebimento → entrada --- #
def _nota(cenario, qtd="50", valor="4"):
    c = cenario
    return compra_service.registrar_nota(
        c["org"].id,
        fornecedor_id=c["forn"].id,
        setor_id=c["setor"].id,
        numero="NF-1",
        itens=[_item("Papel", qtd, valor, c["prod"].id)],
    )


def test_recebimento_definitivo_dispara_entrada_valorada(cenario):
    c = cenario
    nota = _nota(cenario, "50", "4")
    publico_service.registrar_recebimento(
        c["org"].id, tipo=RECEB_DEFINITIVO, nota_fiscal_id=nota.id, setor_id=c["setor"].id
    )
    db.session.refresh(nota)
    assert nota.status == NF_LANCADA
    saldo = estoque_service.obter_saldo(c["prod"].id, c["setor"].id)
    assert saldo.quantidade == Decimal("50.000")


def test_recebimento_provisorio_nao_lanca(cenario):
    c = cenario
    nota = _nota(cenario)
    publico_service.registrar_recebimento(
        c["org"].id, tipo=RECEB_PROVISORIO, nota_fiscal_id=nota.id, setor_id=c["setor"].id
    )
    db.session.refresh(nota)
    assert nota.status != NF_LANCADA


# ------------------------------------------------ Liquidação e pagamento --- #
def test_liquidacao_parcial_e_total(cenario):
    c = cenario
    emp = publico_service.emitir_empenho(c["org"].id, valor="1000", dotacao_id=c["dot"].id)
    publico_service.liquidar(c["org"].id, empenho_id=emp.id, valor="400")
    db.session.refresh(emp)
    assert emp.status == EMP_PARC_LIQUIDADO
    assert emp.saldo_a_liquidar == Decimal("600.00")
    publico_service.liquidar(c["org"].id, empenho_id=emp.id, valor="600")
    db.session.refresh(emp)
    assert emp.status == EMP_LIQUIDADO
    assert emp.saldo_a_liquidar == Decimal("0.00")


def test_liquidacao_acima_do_saldo_bloqueia(cenario):
    c = cenario
    emp = publico_service.emitir_empenho(c["org"].id, valor="500", dotacao_id=c["dot"].id)
    with pytest.raises(ErroPublico, match="saldo a liquidar"):
        publico_service.liquidar(c["org"].id, empenho_id=emp.id, valor="600")


def test_liquidacao_exige_recebimento_definitivo(cenario):
    c = cenario
    nota = _nota(cenario)
    emp = publico_service.emitir_empenho(c["org"].id, valor="500", dotacao_id=c["dot"].id)
    receb = publico_service.registrar_recebimento(
        c["org"].id, tipo=RECEB_PROVISORIO, nota_fiscal_id=nota.id, setor_id=c["setor"].id
    )
    with pytest.raises(ErroPublico, match="recebimento definitivo"):
        publico_service.liquidar(
            c["org"].id, empenho_id=emp.id, valor="200", recebimento_id=receb.id
        )


def test_anular_empenho_liquidado_falha(cenario):
    c = cenario
    emp = publico_service.emitir_empenho(c["org"].id, valor="500", dotacao_id=c["dot"].id)
    publico_service.liquidar(c["org"].id, empenho_id=emp.id, valor="100")
    with pytest.raises(ErroPublico, match="já liquidado"):
        publico_service.anular_empenho(emp)


def test_pagamento_baixa_saldo_da_liquidacao(cenario):
    c = cenario
    emp = publico_service.emitir_empenho(c["org"].id, valor="500", dotacao_id=c["dot"].id)
    liq = publico_service.liquidar(c["org"].id, empenho_id=emp.id, valor="500")
    publico_service.pagar(c["org"].id, liquidacao_id=liq.id, valor="300")
    db.session.refresh(liq)
    assert liq.valor_pago == Decimal("300.00")
    publico_service.pagar(c["org"].id, liquidacao_id=liq.id, valor="200")
    db.session.refresh(liq)
    assert liq.status == LIQ_PAGA
    with pytest.raises(ErroPublico, match="saldo da liquidação"):
        publico_service.pagar(c["org"].id, liquidacao_id=liq.id, valor="1")
