"""Testes de rota das transferências: envio, recebimento e RBAC por escopo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.rbac import Papel, UsuarioPapel
from app.models.setor import Setor
from app.models.transferencia import ENVIADA, RECEBIDA, Transferencia
from app.models.usuario import Usuario
from app.services import estoque_service, produto_service, setor_service, setup
from tests.conftest import login


def _operador(org, setor_id, username):
    u = Usuario(
        organizacao_id=org.id,
        nome=username,
        email=f"{username}@t.local",
        username=username,
        deve_trocar_senha=False,
    )
    u.definir_senha("Senha@12345")
    db.session.add(u)
    db.session.flush()
    papel = db.session.query(Papel).filter_by(organizacao_id=org.id, nome="Operador").one()
    db.session.add(UsuarioPapel(usuario_id=u.id, papel_id=papel.id, setor_id=setor_id))
    db.session.commit()
    return u


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org TR", slug="tr", commit=False)
    db.session.commit()
    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    a = setor_service.criar_setor(org.id, nome="A", setor_pai_id=central.id)
    b = setor_service.criar_setor(org.id, nome="B", setor_pai_id=central.id)
    prod = produto_service.criar_produto(org.id, nome="Papel", unidade="UN")
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=a.id, quantidade=50)
    return {"org": org, "a": a, "b": b, "prod": prod}


def test_enviar_via_rota(client, cenario):
    org, a, b, prod = cenario.values()
    _operador(org, a.id, "opa")
    login(client, identificador="opa")
    resp = client.post(
        "/transferencias/nova",
        data={
            "setor_origem_id": a.id,
            "setor_destino_id": b.id,
            "produto_id": prod.id,
            "quantidade": "20",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    t = db.session.query(Transferencia).filter_by(organizacao_id=org.id).one()
    assert t.status == ENVIADA
    assert estoque_service.obter_saldo(prod.id, a.id).quantidade_em_transito == Decimal("20.000")


def test_destino_recebe_origem_nao(client, cenario):
    org, a, b, prod = cenario.values()
    from app.services import transferencia_service as ts

    t = ts.enviar(
        org.id,
        setor_origem_id=a.id,
        setor_destino_id=b.id,
        itens=[{"produto_id": prod.id, "quantidade": 10}],
    )
    db.session.commit()

    # Operador da origem (A) NÃO pode receber (não é o destino).
    _operador(org, a.id, "opa")
    login(client, identificador="opa")
    resp = client.get(f"/transferencias/{t.id}/receber")
    assert resp.status_code == 403

    # Operador do destino (B) pode receber.
    client.get("/logout")
    _operador(org, b.id, "opb")
    login(client, identificador="opb")
    resp = client.post(
        f"/transferencias/{t.id}/receber",
        data={
            f"recebida_{t.itens[0].id}": "10",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(t)
    assert t.status == RECEBIDA
    assert estoque_service.obter_saldo(prod.id, b.id).quantidade == Decimal("10.000")
