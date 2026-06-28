"""Testes de rotas de empréstimos: páginas, criação e devolução."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.ativo import EM_ESTOQUE, Ativo
from app.models.emprestimo import Emprestimo
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
    ativo = Ativo(
        organizacao_id=org.id, nome="Projetor", status_ciclo=EM_ESTOQUE, setor_atual_id=setor.id
    )
    db.session.add(ativo)
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "ativo": ativo}


def test_paginas_carregam(base, client):
    login(client)
    for url in ("/emprestimos/", "/emprestimos/novo", "/emprestimos/recibos",
                "/emprestimos/?filtro=vencidos", "/emprestimos/?filtro=devolvidos"):
        assert client.get(url).status_code == 200, url


def test_emprestar_e_devolver_consumivel(base, client):
    login(client)
    resp = client.post(
        "/emprestimos/novo",
        data={
            "tipo": "CONSUMIVEL", "produto_id": base["prod"].id, "quantidade": "4",
            "ativo_id": 0, "setor_id": base["setor"].id,
            "destinatario": "João", "responsavel_id": 0,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    emp = db.session.query(Emprestimo).one()
    assert emp.quantidade == Decimal("4.000")
    saldo = estoque_service.obter_saldo(base["prod"].id, base["setor"].id)
    assert saldo.quantidade == Decimal("6.000")

    client.post(f"/emprestimos/{emp.id}/devolver", data={"quantidade": "4"}, follow_redirects=True)
    db.session.refresh(emp)
    assert emp.status == "DEVOLVIDO"
    saldo = estoque_service.obter_saldo(base["prod"].id, base["setor"].id)
    assert saldo.quantidade == Decimal("10.000")


def test_emprestar_durable_pela_rota(base, client):
    login(client)
    client.post(
        "/emprestimos/novo",
        data={
            "tipo": "DURAVEL", "ativo_id": base["ativo"].id, "produto_id": 0,
            "quantidade": "1", "setor_id": base["setor"].id,
            "destinatario": "TI", "responsavel_id": 0,
        },
        follow_redirects=True,
    )
    emp = db.session.query(Emprestimo).one()
    assert emp.is_duravel
    db.session.refresh(base["ativo"])
    assert base["ativo"].status_ciclo == "EMPRESTADO"
