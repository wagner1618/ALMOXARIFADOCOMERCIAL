"""Testes de rotas de compras: fornecedores, pedidos e notas fiscais."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.compras import APROVADO, NF_LANCADA, NotaFiscal, PedidoCompra
from app.models.fornecedor import Fornecedor
from app.models.setor import Setor
from app.services import produto_service
from tests.conftest import login


@pytest.fixture()
def base(org):
    """Org com setor de compra habilitado, um produto e um fornecedor."""
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    setor.poder_compra = True
    setor.orcamento_anual = Decimal("50000.00")
    prod = produto_service.criar_produto(org.id, nome="Papel A4", unidade="RESMA", commit=False)
    forn = Fornecedor(organizacao_id=org.id, nome="Papelaria X", documento="222")
    db.session.add(forn)
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "forn": forn}


def test_paginas_carregam(base, client):
    login(client)
    for url in ("/compras/fornecedores", "/compras/pedidos", "/compras/notas",
                "/compras/fornecedores/novo", "/compras/pedidos/novo", "/compras/notas/nova"):
        assert client.get(url).status_code == 200


def test_criar_fornecedor(base, client):
    login(client)
    resp = client.post(
        "/compras/fornecedores/novo",
        data={"nome": "Nova Forn", "tipo_pessoa": "PJ", "documento": "999"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert db.session.query(Fornecedor).filter_by(documento="999").count() == 1


def test_criar_e_aprovar_pedido(base, client):
    login(client)
    resp = client.post(
        "/compras/pedidos/novo",
        data={
            "setor_id": base["setor"].id,
            "fornecedor_id": base["forn"].id,
            "item_produto_id": [str(base["prod"].id)],
            "item_descricao": ["Papel"],
            "item_quantidade": ["10"],
            "item_valor_unitario": ["5"],
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    pedido = db.session.query(PedidoCompra).one()
    assert pedido.valor_estimado == Decimal("50.00")

    resp = client.post(f"/compras/pedidos/{pedido.id}/aprovar", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(pedido)
    assert pedido.status == APROVADO


def test_criar_e_lancar_nota(base, client):
    login(client)
    resp = client.post(
        "/compras/notas/nova",
        data={
            "fornecedor_id": base["forn"].id,
            "setor_id": base["setor"].id,
            "numero": "5005",
            "serie": "1",
            "item_produto_id": [str(base["prod"].id)],
            "item_descricao": ["Papel"],
            "item_quantidade": ["8"],
            "item_valor_unitario": ["3"],
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    nota = db.session.query(NotaFiscal).one()
    assert nota.valor_total == Decimal("24.00")

    resp = client.post(f"/compras/notas/{nota.id}/lancar", follow_redirects=True)
    assert resp.status_code == 200
    db.session.refresh(nota)
    assert nota.status == NF_LANCADA


def test_setor_sem_poder_compra_nao_aparece(base, client):
    """O choices de setor de compra só lista setores habilitados."""
    base["setor"].poder_compra = False
    db.session.commit()
    login(client)
    client.post(
        "/compras/pedidos/novo",
        data={
            "setor_id": base["setor"].id,
            "fornecedor_id": 0,
            "item_descricao": ["X"],
            "item_quantidade": ["1"],
            "item_valor_unitario": ["1"],
        },
        follow_redirects=True,
    )
    # SelectField rejeita a opção fora do choices → nenhum pedido criado.
    assert db.session.query(PedidoCompra).count() == 0
