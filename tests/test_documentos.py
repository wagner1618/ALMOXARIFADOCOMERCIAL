"""Testes do serviço de documentos (§7.7): numeração, hash, snapshot, vínculo, sandbox."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.documento import TIPOS_DOCUMENTO, ModeloDocumento
from app.models.setor import Setor
from app.services import documento_service, estoque_service, produto_service


@pytest.fixture()
def docenv(app, tmp_path, org):
    """Aponta o UPLOAD_DIR para um diretório temporário e devolve a org."""
    app.config["UPLOAD_DIR"] = str(tmp_path)
    return org


def test_seed_cria_um_modelo_por_tipo(docenv):
    assert db.session.query(ModeloDocumento).count() == len(TIPOS_DOCUMENTO)


def test_emitir_gera_numero_hash_snapshot(docenv):
    doc = documento_service.emitir(
        docenv.id, tipo="SAIDA",
        contexto={"itens": [{"descricao": "Papel", "quantidade": "2"}]},
        commit=False,
    )
    db.session.flush()
    assert doc.numero == f"SAIDA-{doc.ano}-000001"
    assert doc.hash and len(doc.hash) == 64
    assert doc.formato in ("pdf", "html")
    assert doc.dados["documento"]["numero"] == doc.numero
    caminho = documento_service.caminho_arquivo(doc)
    assert caminho.exists()


def test_numeracao_incrementa_por_tipo(docenv):
    d1 = documento_service.emitir(docenv.id, tipo="SAIDA", contexto={}, commit=False)
    db.session.flush()
    d2 = documento_service.emitir(docenv.id, tipo="SAIDA", contexto={}, commit=False)
    db.session.flush()
    outro = documento_service.emitir(docenv.id, tipo="BAIXA", contexto={}, commit=False)
    db.session.flush()
    assert d2.sequencial == d1.sequencial + 1
    assert outro.sequencial == 1  # sequência independente por tipo


def test_emitir_de_movimentacao_vincula(docenv):
    setor = db.session.query(Setor).filter_by(codigo="CENTRAL").one()
    prod = produto_service.criar_produto(docenv.id, nome="Cabo", unidade="UN", commit=False)
    db.session.flush()
    estoque_service.entrada(
        docenv.id, produto_id=prod.id, setor_id=setor.id, quantidade=5, commit=False
    )
    mov = estoque_service.saida(
        docenv.id, produto_id=prod.id, setor_id=setor.id, quantidade=2, commit=False
    )
    db.session.flush()
    doc = documento_service.emitir_de_movimentacao(mov, commit=False)
    db.session.flush()
    assert mov.documento_id == doc.id
    assert doc.tipo == "SAIDA"


def test_render_sandbox_escapa_html():
    html = documento_service.renderizar_html("Olá {{ nome }}", {"nome": "<b>x</b>"})
    assert "Olá" in html
    assert "&lt;b&gt;" in html  # autoescape ativo
