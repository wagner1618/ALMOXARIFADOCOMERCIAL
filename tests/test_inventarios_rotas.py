"""Testes de rotas de inventário: abrir, contar e fechar."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.inventario import Inventario
from app.models.setor import Setor
from app.services import estoque_service, produto_service
from tests.conftest import login


@pytest.fixture()
def base(org):
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    prod = produto_service.criar_produto(org.id, nome="Cabo", unidade="UN", commit=False)
    db.session.flush()
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10, commit=False
    )
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod}


def test_paginas_carregam(base, client):
    login(client)
    for url in ("/inventarios/", "/inventarios/novo"):
        assert client.get(url).status_code == 200, url


def test_abrir_contar_fechar(base, client):
    login(client)
    resp = client.post(
        "/inventarios/novo",
        data={"tipo": "CONSUMIVEL", "setor_id": base["setor"].id},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    inv = db.session.query(Inventario).one()
    assert inv.total_itens == 1
    item = inv.itens[0]

    client.post(
        f"/inventarios/{inv.id}/contar",
        data={f"qtd_{item.id}": "7"},
        follow_redirects=True,
    )
    db.session.refresh(item)
    assert item.contado and item.divergencia

    client.post(f"/inventarios/{inv.id}/fechar", follow_redirects=True)
    db.session.refresh(inv)
    assert inv.status == "FECHADO"
    saldo = estoque_service.obter_saldo(base["prod"].id, base["setor"].id)
    assert saldo.quantidade == Decimal("7.000")
