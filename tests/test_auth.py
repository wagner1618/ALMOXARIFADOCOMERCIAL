"""Testes de autenticação e fluxo de login."""

from __future__ import annotations

from tests.conftest import login


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_login_pagina_renderiza(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Controle de almoxarifado" in resp.get_data(as_text=True)


def test_login_sucesso_redireciona_dashboard(client, org):
    resp = login(client)
    assert resp.status_code == 200
    corpo = resp.get_data(as_text=True)
    assert "Painel" in corpo
    assert "Org Teste" in corpo


def test_login_senha_errada(client, org):
    resp = login(client, senha="errada")
    assert resp.status_code == 401
    assert "inválidos" in resp.get_data(as_text=True)


def test_login_por_email(client, org):
    resp = login(client, identificador="admin@teste.local")
    assert resp.status_code == 200
    assert "Painel" in resp.get_data(as_text=True)


def test_dashboard_exige_login(client, org):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout(client, org):
    login(client)
    resp = client.get("/logout", follow_redirects=True)
    assert resp.status_code == 200
    assert "Sessão encerrada" in resp.get_data(as_text=True)
