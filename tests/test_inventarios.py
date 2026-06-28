"""Testes do serviço de inventário (§8): recontagem de consumíveis e recertificação de ativos."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.ativo import BOM, EM_USO, REGULAR, Ativo
from app.models.movimentacao import AJUSTE_INVENTARIO, Movimentacao
from app.models.setor import Setor
from app.services import estoque_service, inventario_service, produto_service
from app.services.inventario_service import ErroInventario


@pytest.fixture()
def base(org):
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    prod = produto_service.criar_produto(org.id, nome="Cabo", unidade="UN", commit=False)
    db.session.flush()
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10, commit=False
    )
    ativo = Ativo(
        organizacao_id=org.id, nome="Projetor", estado_conservacao=BOM,
        status_ciclo=EM_USO, setor_atual_id=setor.id,
    )
    db.session.add(ativo)
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "ativo": ativo}


def test_recontagem_consumivel_ajusta_saldo(base):
    c = base
    inv = inventario_service.abrir_inventario(
        c["org"].id, tipo="CONSUMIVEL", setor_id=c["setor"].id, commit=False
    )
    db.session.flush()
    assert inv.total_itens == 1
    item = inv.itens[0]
    assert item.quantidade_esperada == Decimal("10.000")

    inventario_service.registrar_contagem(item, quantidade="8", commit=False)
    assert item.divergencia is True

    inventario_service.fechar_inventario(inv, commit=False)
    db.session.flush()
    assert inv.status == "FECHADO"
    saldo = estoque_service.obter_saldo(c["prod"].id, c["setor"].id)
    assert saldo.quantidade == Decimal("8.000")
    assert db.session.query(Movimentacao).filter_by(tipo=AJUSTE_INVENTARIO).count() == 1


def test_sem_divergencia_nao_gera_ajuste(base):
    c = base
    inv = inventario_service.abrir_inventario(
        c["org"].id, tipo="CONSUMIVEL", setor_id=c["setor"].id, commit=False
    )
    db.session.flush()
    inventario_service.registrar_contagem(inv.itens[0], quantidade="10", commit=False)
    inventario_service.fechar_inventario(inv, commit=False)
    db.session.flush()
    assert db.session.query(Movimentacao).filter_by(tipo=AJUSTE_INVENTARIO).count() == 0


def test_recertificacao_ativo_atualiza_estado_e_revisao(base):
    c = base
    inv = inventario_service.abrir_inventario(
        c["org"].id, tipo="ATIVO", setor_id=c["setor"].id, commit=False
    )
    db.session.flush()
    assert inv.total_itens == 1
    item = inv.itens[0]
    assert item.estado_conservacao == BOM

    inventario_service.registrar_contagem(item, estado_conservacao=REGULAR, commit=False)
    assert item.divergencia is True

    inventario_service.fechar_inventario(inv, commit=False)
    db.session.flush()
    db.session.refresh(c["ativo"])
    assert c["ativo"].estado_conservacao == REGULAR
    assert c["ativo"].ultima_revisao_em == date.today()
    assert c["ativo"].proxima_revisao_em == date.today() + timedelta(days=365)


def test_alerta_revisao_vencida(base):
    c = base
    c["ativo"].proxima_revisao_em = date.today() - timedelta(days=1)
    db.session.commit()
    vencidos = inventario_service.ativos_revisao_vencida(c["org"].id)
    assert c["ativo"] in vencidos


def test_fechar_exige_aberto(base):
    c = base
    inv = inventario_service.abrir_inventario(
        c["org"].id, tipo="CONSUMIVEL", setor_id=c["setor"].id, commit=False
    )
    db.session.flush()
    inventario_service.fechar_inventario(inv, commit=False)
    with pytest.raises(ErroInventario):
        inventario_service.fechar_inventario(inv, commit=False)
