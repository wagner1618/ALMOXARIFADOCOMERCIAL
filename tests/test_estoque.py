"""Testes do serviço de estoque: entrada, saída, saldo, custo médio, lote, ajuste."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.movimentacao import AJUSTE_INVENTARIO, ENTRADA, SAIDA, Movimentacao
from app.models.produto import TIPO_DURAVEL
from app.services import estoque_service, produto_service, setup
from app.services.estoque_service import ErroEstoque


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org Estoque", slug="estoque")
    from app.models.setor import Setor

    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    prod = produto_service.criar_produto(org.id, nome="Papel", unidade="RESMA", estoque_minimo=10)
    return {"org": org, "setor": central, "prod": prod}


def test_entrada_soma_saldo(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=100)
    saldo = estoque_service.obter_saldo(prod.id, setor.id)
    assert saldo.quantidade == Decimal("100.000")


def test_saida_subtrai_e_bloqueia_negativo(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=30)
    estoque_service.saida(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10)
    assert estoque_service.obter_saldo(prod.id, setor.id).quantidade == Decimal("20.000")
    with pytest.raises(ErroEstoque):
        estoque_service.saida(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=999)


def test_quantidade_zero_ou_negativa_falha(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    with pytest.raises(ErroEstoque):
        estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=0)


def test_custo_medio_ponderado(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10, valor_unitario=2
    )
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10, valor_unitario=4
    )
    db.session.refresh(prod)
    # (10*2 + 10*4) / 20 = 3
    assert prod.custo_medio == Decimal("3.0000")


def test_duravel_nao_tem_saldo(cenario):
    org, setor = cenario["org"], cenario["setor"]
    duravel = produto_service.criar_produto(org.id, nome="Notebook", tipo_controle=TIPO_DURAVEL)
    with pytest.raises(ErroEstoque):
        estoque_service.entrada(org.id, produto_id=duravel.id, setor_id=setor.id, quantidade=1)


def test_movimentacoes_append_only(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=5)
    estoque_service.saida(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=2)
    movs = db.session.query(Movimentacao).filter_by(organizacao_id=org.id).all()
    assert {m.tipo for m in movs} == {ENTRADA, SAIDA}


def test_lote_atomico_falha_nao_grava(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=5)
    # Lote com uma saída válida e uma inválida (saldo insuficiente) -> nada grava.
    ops = [
        {"tipo": SAIDA, "produto_id": prod.id, "setor_id": setor.id, "quantidade": 2},
        {"tipo": SAIDA, "produto_id": prod.id, "setor_id": setor.id, "quantidade": 999},
    ]
    with pytest.raises(ErroEstoque):
        estoque_service.processar_lote(org.id, operacoes=ops)
    # Saldo permanece 5 (lote não aplicado).
    assert estoque_service.obter_saldo(prod.id, setor.id).quantidade == Decimal("5.000")


def test_lote_entrada_sucesso(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    prod2 = produto_service.criar_produto(org.id, nome="Caneta", unidade="UN")
    ops = [
        {"tipo": ENTRADA, "produto_id": prod.id, "setor_id": setor.id, "quantidade": 10},
        {"tipo": ENTRADA, "produto_id": prod2.id, "setor_id": setor.id, "quantidade": 50},
    ]
    lote = estoque_service.processar_lote(org.id, operacoes=ops)
    assert lote.numero == 1
    assert estoque_service.obter_saldo(prod.id, setor.id).quantidade == Decimal("10.000")
    assert estoque_service.obter_saldo(prod2.id, setor.id).quantidade == Decimal("50.000")


def test_ajuste_inventario(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=20)
    estoque_service.ajustar(
        org.id,
        produto_id=prod.id,
        setor_id=setor.id,
        nova_quantidade=15,
        justificativa="Recontagem física",
    )
    assert estoque_service.obter_saldo(prod.id, setor.id).quantidade == Decimal("15.000")
    mov = db.session.query(Movimentacao).filter_by(tipo=AJUSTE_INVENTARIO).one()
    assert mov.quantidade == Decimal("5.000")  # diferença


def test_ajuste_exige_justificativa(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    with pytest.raises(ErroEstoque):
        estoque_service.ajustar(
            org.id, produto_id=prod.id, setor_id=setor.id, nova_quantidade=5, justificativa=""
        )
