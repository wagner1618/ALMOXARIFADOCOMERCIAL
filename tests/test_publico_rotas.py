"""Testes de rotas das compras públicas (§7.10): gating de modo e cadeia da despesa."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.fornecedor import Fornecedor
from app.models.publico import (
    Contrato,
    DotacaoOrcamentaria,
    Empenho,
    Liquidacao,
    Pagamento,
    ProcessoContratacao,
    Recebimento,
)
from app.models.setor import Setor
from tests.conftest import login


@pytest.fixture()
def org_publica(org):
    """Coloca a organização em modo PÚBLICO e cria um fornecedor."""
    org.config = {"modo_compra": "PUBLICO"}
    forn = Fornecedor(organizacao_id=org.id, nome="Fornecedor Público", documento="111")
    db.session.add(forn)
    db.session.commit()
    return {"org": org, "forn": forn}


def test_modo_privado_bloqueia(org, client):
    """Em modo PRIVADO o módulo público responde 404."""
    login(client)
    assert client.get("/publico/dotacoes").status_code == 404


def test_paginas_carregam(org_publica, client):
    login(client)
    for url in (
        "/publico/dotacoes", "/publico/dotacoes/nova",
        "/publico/processos", "/publico/processos/novo",
        "/publico/atas", "/publico/atas/nova",
        "/publico/contratos", "/publico/contratos/novo",
        "/publico/empenhos", "/publico/empenhos/novo",
        "/publico/recebimentos", "/publico/recebimentos/novo",
        "/publico/liquidacoes",
    ):
        assert client.get(url).status_code == 200, url


def test_cadeia_da_despesa(org_publica, client):
    """Dotação → contrato → empenho → liquidação → pagamento pelas rotas."""
    c = org_publica
    login(client)

    # Dotação de R$ 1.000
    client.post("/publico/dotacoes/nova", data={"valor_dotado": "1000"}, follow_redirects=True)
    dot = db.session.query(DotacaoOrcamentaria).one()
    assert dot.valor_dotado == Decimal("1000.00")

    # Processo de contratação
    client.post(
        "/publico/processos/novo",
        data={
            "numero_processo": "001/2026", "objeto": "Aquisição de papel",
            "modalidade": "PREGAO", "procedimento_auxiliar": "NENHUM", "setor_id": 0,
        },
        follow_redirects=True,
    )
    assert db.session.query(ProcessoContratacao).count() == 1

    # Contrato com item (10 × 50 = 500)
    client.post(
        "/publico/contratos/novo",
        data={
            "numero": "CT-01", "objeto": "Papel A4", "fornecedor_id": c["forn"].id,
            "processo_id": 0, "ata_id": 0, "fiscal_id": 0, "gestor_id": 0,
            "item_descricao": ["Papel A4"],
            "item_quantidade": ["10"],
            "item_valor_unitario": ["50"],
        },
        follow_redirects=True,
    )
    contrato = db.session.query(Contrato).one()
    assert contrato.valor_global == Decimal("500.00")

    # Empenho de R$ 500 sobre a dotação e o contrato
    client.post(
        "/publico/empenhos/novo",
        data={
            "dotacao_id": dot.id, "tipo": "ORDINARIO", "valor": "500",
            "contrato_id": contrato.id, "ata_id": 0, "processo_id": 0, "fornecedor_id": 0,
        },
        follow_redirects=True,
    )
    empenho = db.session.query(Empenho).one()
    assert empenho.saldo_a_liquidar == Decimal("500.00")
    db.session.refresh(dot)
    assert dot.saldo_disponivel == Decimal("500.00")  # 1000 - 500 empenhado
    db.session.refresh(contrato)
    assert contrato.saldo_valor == Decimal("0.00")  # contrato totalmente empenhado

    # Liquidação total
    client.post(
        f"/publico/empenhos/{empenho.id}/liquidar",
        data={"valor": "500", "nota_fiscal_id": 0, "recebimento_id": 0},
        follow_redirects=True,
    )
    liq = db.session.query(Liquidacao).one()
    assert liq.valor == Decimal("500.00")
    db.session.refresh(empenho)
    assert empenho.status == "LIQUIDADO"

    # Pagamento total → liquidação fica PAGA
    client.post(
        f"/publico/liquidacoes/{liq.id}/pagar",
        data={"valor": "500", "ordem_bancaria": "OB-1"},
        follow_redirects=True,
    )
    assert db.session.query(Pagamento).count() == 1
    db.session.refresh(liq)
    assert liq.status == "PAGA"


def test_empenho_acima_do_saldo_falha(org_publica, client):
    login(client)
    client.post("/publico/dotacoes/nova", data={"valor_dotado": "100"}, follow_redirects=True)
    dot = db.session.query(DotacaoOrcamentaria).one()
    resp = client.post(
        "/publico/empenhos/novo",
        data={"dotacao_id": dot.id, "tipo": "ORDINARIO", "valor": "500",
              "contrato_id": 0, "ata_id": 0, "processo_id": 0, "fornecedor_id": 0},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert db.session.query(Empenho).count() == 0  # rejeitado por exceder a dotação


def test_recebimento_provisorio(org_publica, client):
    login(client)
    setor = db.session.query(Setor).filter_by(codigo="CENTRAL").one()
    client.post(
        "/publico/recebimentos/novo",
        data={"tipo": "PROVISORIO", "nota_fiscal_id": 0, "empenho_id": 0,
              "contrato_id": 0, "setor_id": setor.id, "conforme": "y"},
        follow_redirects=True,
    )
    assert db.session.query(Recebimento).count() == 1
