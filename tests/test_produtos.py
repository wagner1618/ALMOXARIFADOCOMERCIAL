"""Testes de produtos: SKU automático, criação, rotas e import/export."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.categoria import Categoria
from app.models.produto import TIPO_DURAVEL, Produto
from app.services import excel, produto_service, setup
from app.services.produto_service import ErroProduto
from tests.conftest import login


@pytest.fixture()
def org_prod(app):
    org = setup.criar_organizacao("Org Prod", slug="prod", commit=False)
    setup.criar_usuario_admin(
        org,
        nome="Admin",
        email="a@p.local",
        username="admin",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    cat = Categoria(organizacao_id=org.id, nome="Informática")
    db.session.add(cat)
    db.session.commit()
    return {"org": org, "cat": cat}


def test_sku_automatico(org_prod):
    p = produto_service.criar_produto(org_prod["org"].id, nome="Caneta")
    assert p.sku == f"PRD-{p.id:06d}"


def test_sku_manual_e_duplicado(org_prod):
    org = org_prod["org"]
    produto_service.criar_produto(org.id, nome="A", sku="ABC")
    with pytest.raises(ErroProduto):
        produto_service.criar_produto(org.id, nome="B", sku="ABC")


def test_tipo_invalido(org_prod):
    with pytest.raises(ErroProduto):
        produto_service.criar_produto(org_prod["org"].id, nome="X", tipo_controle="OUTRO")


def test_criar_produto_via_rota_com_campos(client, org_prod):
    org, cat = org_prod["org"], org_prod["cat"]
    # cria um campo customizado obrigatório para a categoria
    from app.models.definicao_campo import ENTIDADE_PRODUTO, TIPO_TEXTO, DefinicaoCampo

    db.session.add(
        DefinicaoCampo(
            organizacao_id=org.id,
            entidade=ENTIDADE_PRODUTO,
            chave="patrimonio",
            rotulo="Patrimônio",
            tipo=TIPO_TEXTO,
            obrigatorio=True,
            aplica_a_categoria_id=cat.id,
        )
    )
    db.session.commit()

    login(client)
    # Sem o campo obrigatório -> permanece na página (não cria)
    resp = client.post(
        "/produtos/novo",
        data={
            "nome": "Notebook",
            "tipo_controle": TIPO_DURAVEL,
            "categoria_id": cat.id,
            "unidade": "UN",
            "estoque_minimo": "0",
            "submit": "Salvar",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert (
        db.session.query(Produto).filter_by(organizacao_id=org.id, nome="Notebook").first() is None
    )

    # Com o campo -> cria
    client.post(
        "/produtos/novo",
        data={
            "nome": "Notebook",
            "tipo_controle": TIPO_DURAVEL,
            "categoria_id": cat.id,
            "unidade": "UN",
            "estoque_minimo": "0",
            "cc_patrimonio": "TOMB-001",
            "submit": "Salvar",
        },
        follow_redirects=True,
    )
    p = db.session.query(Produto).filter_by(organizacao_id=org.id, nome="Notebook").first()
    assert p is not None
    assert p.campos["patrimonio"] == "TOMB-001"


def test_exportar_importar_excel(app, org_prod):
    org, cat = org_prod["org"], org_prod["cat"]
    produto_service.criar_produto(org.id, nome="Mouse", categoria_id=cat.id, unidade="UN")

    conteudo = excel.exportar_produtos(org.id)
    assert conteudo[:2] == b"PK"  # xlsx é um zip

    # Importa uma planilha nova com 1 produto novo e 1 atualização (mesmo nome via SKU).
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append([rot for _, rot in excel.COLUNAS_FIXAS])
    ws.append(["", "Teclado", "CONSUMIVEL", "Informática", "UN", 5, "", "Logitech", "", "", ""])
    ws.append(["", "", "CONSUMIVEL", "", "UN", "", "", "", "", "", ""])  # linha inválida (sem nome)
    import io

    buf = io.BytesIO()
    wb.save(buf)
    resultado = excel.importar_produtos(org.id, buf.getvalue())
    assert resultado["criados"] == 1
    assert len(resultado["erros"]) == 1
    assert db.session.query(Produto).filter_by(organizacao_id=org.id, nome="Teclado").first()


def test_listar_produtos_busca(client, org_prod):
    org = org_prod["org"]
    produto_service.criar_produto(org.id, nome="Cadeira Gamer")
    produto_service.criar_produto(org.id, nome="Mesa")
    login(client)
    resp = client.get("/produtos/?q=Cadeira")
    corpo = resp.get_data(as_text=True)
    assert "Cadeira Gamer" in corpo
    assert "Mesa" not in corpo
