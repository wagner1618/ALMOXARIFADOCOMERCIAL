"""Fixtures de teste: app em modo testing (SQLite em memória) + dados base."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db as _db
from app.services import setup


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def org(app):
    """Organização demo com setores e um admin (senha conhecida)."""
    organizacao = setup.criar_organizacao("Org Teste", slug="teste", commit=False)
    setup.criar_usuario_admin(
        organizacao,
        nome="Admin Teste",
        email="admin@teste.local",
        username="admin",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    _db.session.commit()
    return organizacao


def login(client, identificador="admin", senha="Senha@12345"):
    """Faz login via test client (CSRF desativado em testing)."""
    return client.post(
        "/login",
        data={"identificador": identificador, "senha": senha},
        follow_redirects=True,
    )
