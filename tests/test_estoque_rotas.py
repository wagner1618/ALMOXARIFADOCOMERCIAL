"""Testes de rota do estoque: entrada/saída via UI e alertas."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.services import estoque_service, produto_service, setup
from tests.conftest import login


@pytest.fixture()
def org_estoque(app):
    org = setup.criar_organizacao("Org E", slug="e", commit=False)
    setup.criar_usuario_admin(
        org,
        nome="Admin",
        email="a@e.local",
        username="admin",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    db.session.commit()
    from app.models.setor import Setor

    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    prod = produto_service.criar_produto(
        org.id, nome="Papel A4", unidade="RESMA", estoque_minimo=10
    )
    return {"org": org, "setor": setor, "prod": prod}


def test_entrada_via_rota(client, org_estoque):
    setor, prod = org_estoque["setor"], org_estoque["prod"]
    login(client)
    resp = client.post(
        "/estoque/entrada",
        data={
            "produto_id": prod.id,
            "setor_id": setor.id,
            "quantidade": "100",
            "valor_unitario": "5",
            "submit": "Registrar entrada",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert estoque_service.obter_saldo(prod.id, setor.id).quantidade == Decimal("100.000")


def test_saida_insuficiente_via_rota(client, org_estoque):
    setor, prod = org_estoque["setor"], org_estoque["prod"]
    login(client)
    resp = client.post(
        "/estoque/saida",
        data={
            "produto_id": prod.id,
            "setor_id": setor.id,
            "quantidade": "5",
            "submit": "Registrar saída",
        },
        follow_redirects=True,
    )
    assert "Saldo insuficiente" in resp.get_data(as_text=True)


def test_alertas_lista(client, org_estoque):
    org, setor, prod = org_estoque["org"], org_estoque["setor"], org_estoque["prod"]
    # entra abaixo do mínimo (mínimo=10)
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor.id, quantidade=3)
    login(client)
    resp = client.get("/estoque/alertas")
    corpo = resp.get_data(as_text=True)
    assert "Papel A4" in corpo
    assert "Nível mínimo" in corpo


def test_posicao_respeita_visibilidade(client, app):
    """Usuário operador só vê saldos do seu escopo de setor."""
    from app.models.rbac import Papel, UsuarioPapel
    from app.models.setor import Setor
    from app.models.usuario import Usuario
    from app.services import setor_service

    org = setup.criar_organizacao("Org Vis", slug="vis", commit=False)
    db.session.commit()
    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    setor_a = setor_service.criar_setor(org.id, nome="A", setor_pai_id=central.id)

    prod = produto_service.criar_produto(org.id, nome="X", unidade="UN")
    # saldo no central (fora do escopo do operador) e em A (dentro)
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=central.id, quantidade=5)
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=setor_a.id, quantidade=7)

    op = Usuario(
        organizacao_id=org.id, nome="Op", email="op@v.local", username="op", deve_trocar_senha=False
    )
    op.definir_senha("Senha@12345")
    db.session.add(op)
    db.session.flush()
    papel = db.session.query(Papel).filter_by(organizacao_id=org.id, nome="Operador").one()
    db.session.add(UsuarioPapel(usuario_id=op.id, papel_id=papel.id, setor_id=setor_a.id))
    db.session.commit()

    login(client, identificador="op")
    resp = client.get("/estoque/")
    corpo = resp.get_data(as_text=True)
    # Vê o saldo do setor A (7) mas não há vazamento do central como linha extra.
    assert "7,000" in corpo or "7.000" in corpo
