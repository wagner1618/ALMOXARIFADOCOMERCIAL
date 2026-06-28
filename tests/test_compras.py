"""Testes do serviço de compras: fornecedor, pedido (alçada/orçamento) e NF valorada."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.ativo import Ativo
from app.models.compras import APROVADO, CONCLUIDO, EMPENHADO, NF_LANCADA, RASCUNHO
from app.models.movimentacao import ENTRADA, Movimentacao
from app.models.produto import TIPO_DURAVEL
from app.models.setor import Setor
from app.services import compra_service, produto_service, setup
from app.services.compra_service import ErroCompra


def _item(descricao, quantidade, valor, produto_id=None):
    return {
        "produto_id": produto_id,
        "descricao": descricao,
        "quantidade": quantidade,
        "valor_unitario": valor,
    }


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org Compras", slug="compras")
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    setor.poder_compra = True
    setor.orcamento_anual = Decimal("10000.00")
    prod = produto_service.criar_produto(org.id, nome="Papel A4", unidade="RESMA")
    duravel = produto_service.criar_produto(org.id, nome="Notebook", tipo_controle=TIPO_DURAVEL)
    forn = compra_service.criar_fornecedor(
        org.id, dados={"nome": "Papelaria X", "documento": "111"}
    )
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "duravel": duravel, "forn": forn}


# --------------------------------------------------------------- Fornecedor --- #
def test_documento_duplicado_falha(cenario):
    org = cenario["org"]
    with pytest.raises(ErroCompra):
        compra_service.criar_fornecedor(org.id, dados={"nome": "Outro", "documento": "111"})


# ------------------------------------------------------------------- Pedido --- #
def test_criar_pedido_calcula_total(cenario):
    org, setor, prod = cenario["org"], cenario["setor"], cenario["prod"]
    pedido = compra_service.criar_pedido(
        org.id,
        setor_id=setor.id,
        fornecedor_id=cenario["forn"].id,
        itens=[
            _item("Papel", "10", "5", prod.id),
            _item("Caneta", "2", "3.50"),
        ],
    )
    assert pedido.status == RASCUNHO
    assert pedido.valor_estimado == Decimal("57.00")
    assert len(pedido.itens) == 2


def test_pedido_setor_sem_poder_compra_falha(cenario):
    org = cenario["org"]
    filho = Setor(
        organizacao_id=org.id, nome="Sem compra", codigo="SC", setor_pai_id=cenario["setor"].id
    )
    db.session.add(filho)
    db.session.flush()
    filho.atualizar_path()
    db.session.commit()
    with pytest.raises(ErroCompra, match="poder de compra"):
        compra_service.criar_pedido(
            org.id, setor_id=filho.id, fornecedor_id=None,
            itens=[_item("X", "1", "1")],
        )


def test_fluxo_aprovacao(cenario):
    org, setor = cenario["org"], cenario["setor"]
    pedido = compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None,
        itens=[_item("X", "1", "100")],
    )
    compra_service.aprovar_pedido(pedido, aprovador_id=None)
    assert pedido.status == APROVADO and pedido.data_aprovacao is not None
    compra_service.empenhar_pedido(pedido)
    assert pedido.status == EMPENHADO
    compra_service.concluir_pedido(pedido)
    assert pedido.status == CONCLUIDO
    # Não dá para empenhar um concluído.
    with pytest.raises(ErroCompra):
        compra_service.empenhar_pedido(pedido)


def test_orcamento_bloqueia_quando_configurado(cenario):
    org, setor = cenario["org"], cenario["setor"]
    org.config = {**org.config, "bloquear_estouro_orcamento": True}
    db.session.commit()
    pedido = compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None,
        itens=[_item("Caro", "1", "20000")],
    )
    with pytest.raises(ErroCompra, match="orçamento"):
        compra_service.aprovar_pedido(pedido)
    assert pedido.status == RASCUNHO


def test_orcamento_apenas_alerta_sem_bloqueio(cenario):
    """Sem a flag, o estouro de orçamento não bloqueia a aprovação."""
    org, setor = cenario["org"], cenario["setor"]
    pedido = compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None,
        itens=[_item("Caro", "1", "20000")],
    )
    compra_service.aprovar_pedido(pedido)
    assert pedido.status == APROVADO
    situacao = compra_service.checar_orcamento(setor, pedido.exercicio, 0)
    assert situacao["excede"] is True


def test_aprovacao_dois_olhos(cenario):
    org, setor = cenario["org"], cenario["setor"]
    org.config = {**org.config, "aprovacao_dois_olhos": True}
    db.session.commit()
    pedido = compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None, solicitante_id=42,
        itens=[_item("X", "1", "1")],
    )
    with pytest.raises(ErroCompra, match="diferente do solicitante"):
        compra_service.aprovar_pedido(pedido, aprovador_id=42)
    compra_service.aprovar_pedido(pedido, aprovador_id=7)
    assert pedido.status == APROVADO


def test_orcamento_consumido_soma_status_comprometidos(cenario):
    org, setor = cenario["org"], cenario["setor"]
    p1 = compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None,
        itens=[_item("A", "1", "1000")],
    )
    compra_service.aprovar_pedido(p1)
    # Rascunho não conta.
    compra_service.criar_pedido(
        org.id, setor_id=setor.id, fornecedor_id=None,
        itens=[_item("B", "1", "500")],
    )
    consumido = compra_service.orcamento_consumido(setor.id, p1.exercicio)
    assert consumido == Decimal("1000.00")


# -------------------------------------------------------------- Nota fiscal --- #
def _nota_consumivel(cenario, qtd="10", valor="4"):
    c = cenario
    return compra_service.registrar_nota(
        c["org"].id,
        fornecedor_id=c["forn"].id,
        setor_id=c["setor"].id,
        numero="1001",
        serie="1",
        itens=[_item("Papel", qtd, valor, c["prod"].id)],
    )


def test_lancar_nota_consumivel_valoriza_estoque(cenario):
    from app.services import estoque_service

    c = cenario
    nota = _nota_consumivel(cenario, qtd="10", valor="4")
    assert nota.valor_total == Decimal("40.00")

    compra_service.lancar_entrada_valorada(nota)
    db.session.refresh(nota)
    assert nota.status == NF_LANCADA

    saldo = estoque_service.obter_saldo(c["prod"].id, c["setor"].id)
    assert saldo.quantidade == Decimal("10.000")
    db.session.refresh(c["prod"])
    assert c["prod"].custo_medio == Decimal("4.0000")

    mov = db.session.query(Movimentacao).filter_by(tipo=ENTRADA, nota_fiscal_id=nota.id).one()
    assert mov.valor_total == Decimal("40.00")


def test_lancar_nota_duravel_cria_ativos(cenario):
    c = cenario
    nota = compra_service.registrar_nota(
        c["org"].id,
        fornecedor_id=c["forn"].id,
        setor_id=c["setor"].id,
        numero="2002",
        itens=[_item("Notebook", "3", "2500", c["duravel"].id)],
    )
    compra_service.lancar_entrada_valorada(nota)
    ativos = db.session.query(Ativo).filter_by(produto_id=c["duravel"].id).all()
    assert len(ativos) == 3
    assert all(a.valor_aquisicao == Decimal("2500.00") for a in ativos)
    assert all(a.setor_atual_id == c["setor"].id for a in ativos)


def test_lancar_nota_idempotente(cenario):
    nota = _nota_consumivel(cenario)
    compra_service.lancar_entrada_valorada(nota)
    with pytest.raises(ErroCompra, match="já foi lançada"):
        compra_service.lancar_entrada_valorada(nota)


def test_nota_item_sem_produto_nao_lanca(cenario):
    c = cenario
    nota = compra_service.registrar_nota(
        c["org"].id,
        fornecedor_id=c["forn"].id,
        setor_id=c["setor"].id,
        numero="3003",
        itens=[{"descricao": "Serviço avulso", "quantidade": "1", "valor_unitario": "100"}],
    )
    with pytest.raises(ErroCompra, match="catálogo"):
        compra_service.lancar_entrada_valorada(nota)


def test_nota_exige_setor_com_poder_compra(cenario):
    c = cenario
    filho = Setor(organizacao_id=c["org"].id, nome="Sem compra", codigo="SC2")
    db.session.add(filho)
    db.session.flush()
    filho.atualizar_path()
    db.session.commit()
    with pytest.raises(ErroCompra, match="poder de compra"):
        compra_service.registrar_nota(
            c["org"].id, fornecedor_id=c["forn"].id, setor_id=filho.id, numero="9",
            itens=[_item("P", "1", "1", c["prod"].id)],
        )
