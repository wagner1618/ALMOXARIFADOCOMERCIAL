"""Testes de rota dos ativos (CRUD e ações de ciclo de vida)."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.ativo import EM_USO, Ativo
from app.services import setor_service, setup
from tests.conftest import login


@pytest.fixture()
def org_ativos(app):
    org = setup.criar_organizacao("Org AT", slug="at", commit=False)
    setup.criar_usuario_admin(
        org,
        nome="Admin",
        email="a@at.local",
        username="admin",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    db.session.commit()
    from app.models.setor import Setor

    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    sala = setor_service.criar_setor(org.id, nome="Sala", setor_pai_id=central.id)
    return {"org": org, "central": central, "sala": sala}


def test_criar_ativo_via_rota(client, org_ativos):
    org, central = org_ativos["org"], org_ativos["central"]
    login(client)
    resp = client.post(
        "/ativos/novo",
        data={
            "nome": "Impressora",
            "tombamento": "TB-100",
            "estado_conservacao": "BOM",
            "setor_atual_id": central.id,
            "produto_id": 0,
            "submit": "Salvar",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    a = db.session.query(Ativo).filter_by(organizacao_id=org.id, nome="Impressora").first()
    assert a is not None and a.tombamento == "TB-100"


def test_tombamento_duplicado_via_rota(client, org_ativos):
    org, central = org_ativos["org"], org_ativos["central"]
    login(client)
    dados = {
        "nome": "X",
        "tombamento": "DUP",
        "estado_conservacao": "BOM",
        "setor_atual_id": central.id,
        "produto_id": 0,
        "submit": "Salvar",
    }
    client.post("/ativos/novo", data=dados, follow_redirects=True)
    resp = client.post("/ativos/novo", data={**dados, "nome": "Y"}, follow_redirects=True)
    assert "já é usado" in resp.get_data(as_text=True)
    assert db.session.query(Ativo).filter_by(organizacao_id=org.id, tombamento="DUP").count() == 1


def test_destinar_e_termo(client, org_ativos):
    org, central, sala = org_ativos.values()
    from app.services import ativo_service

    a = ativo_service.criar_ativo(
        org.id,
        dados={
            "nome": "Cadeira",
            "estado_conservacao": "BOM",
            "setor_atual_id": central.id,
        },
    )
    login(client)
    client.post(
        f"/ativos/{a.id}/destinar",
        data={
            "setor_id": sala.id,
            "responsavel_id": 0,
            "submit": "Destinar (gerar termo)",
        },
        follow_redirects=True,
    )
    db.session.refresh(a)
    assert a.status_ciclo == EM_USO
    # Termo disponível para ativo em uso.
    resp = client.get(f"/ativos/{a.id}/termo")
    assert resp.status_code == 200
    assert "Termo de Responsabilidade" in resp.get_data(as_text=True)
