"""Testes de rotas de documentos: busca, emissão a partir de movimentação, download, modelos."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.documento import Documento, ModeloDocumento
from app.models.setor import Setor
from app.services import estoque_service, produto_service
from tests.conftest import login


@pytest.fixture()
def base(app, tmp_path, org):
    app.config["UPLOAD_DIR"] = str(tmp_path)
    setor = db.session.query(Setor).filter_by(codigo="CENTRAL").one()
    prod = produto_service.criar_produto(org.id, nome="Cabo", unidade="UN", commit=False)
    db.session.flush()
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=5, commit=False
    )
    mov = estoque_service.saida(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=2, commit=False
    )
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "mov": mov}


def test_paginas_carregam(base, client):
    login(client)
    for url in ("/documentos/", "/documentos/modelos"):
        assert client.get(url).status_code == 200, url


def test_emitir_de_movimentacao_e_baixar(base, client):
    login(client)
    mov_id = base["mov"].id
    resp = client.post(f"/documentos/emitir/movimentacao/{mov_id}", follow_redirects=True)
    assert resp.status_code == 200
    doc = db.session.query(Documento).one()
    db.session.refresh(base["mov"])
    assert base["mov"].documento_id == doc.id

    # reemitir não duplica
    client.post(f"/documentos/emitir/movimentacao/{mov_id}", follow_redirects=True)
    assert db.session.query(Documento).count() == 1

    assert client.get(f"/documentos/{doc.id}/baixar").status_code == 200
    assert client.get(f"/documentos/{doc.id}/reimprimir").status_code == 200


def test_editar_modelo(base, client):
    login(client)
    modelo = db.session.query(ModeloDocumento).filter_by(tipo="SAIDA").one()
    assert client.get(f"/documentos/modelos/{modelo.id}/editar").status_code == 200
    resp = client.post(
        f"/documentos/modelos/{modelo.id}/editar",
        data={
            "nome": "Saída custom",
            "conteudo_html": "<p>{{ documento.numero }}</p>",
            "ativo": "y",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(modelo)
    assert modelo.nome == "Saída custom"
