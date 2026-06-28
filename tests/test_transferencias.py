"""Testes do fluxo de transferência com confirmação (§7.8)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.models.transferencia import (
    CANCELADA,
    CORRIGIDA,
    RECEBIDA,
    RECEBIDA_COM_DIVERGENCIA,
)
from app.services import estoque_service, produto_service, setor_service, setup
from app.services import transferencia_service as ts
from app.services.transferencia_service import ErroTransferencia


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org T", slug="t")
    from app.models.setor import Setor

    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    destino = setor_service.criar_setor(org.id, nome="Setor B", setor_pai_id=central.id)
    prod = produto_service.criar_produto(org.id, nome="Papel", unidade="RESMA")
    estoque_service.entrada(org.id, produto_id=prod.id, setor_id=central.id, quantidade=100)
    return {"org": org, "origem": central, "destino": destino, "prod": prod}


def _saldo(prod_id, setor_id):
    return estoque_service.obter_saldo(prod_id, setor_id)


def test_enviar_reserva_em_transito(cenario):
    org, origem, destino, prod = cenario.values()
    ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 30}],
    )
    s = _saldo(prod.id, origem.id)
    assert s.quantidade == Decimal("100.000")  # quantidade física intacta
    assert s.quantidade_em_transito == Decimal("30.000")
    assert s.disponivel == Decimal("70.000")  # não disponível
    # Destino ainda não tem nada.
    assert _saldo(prod.id, destino.id) is None


def test_enviar_saldo_insuficiente(cenario):
    org, origem, destino, prod = cenario.values()
    with pytest.raises(ErroTransferencia):
        ts.enviar(
            org.id,
            setor_origem_id=origem.id,
            setor_destino_id=destino.id,
            itens=[{"produto_id": prod.id, "quantidade": 999}],
        )


def test_origem_destino_iguais(cenario):
    org, origem, _destino, prod = cenario.values()
    with pytest.raises(ErroTransferencia):
        ts.enviar(
            org.id,
            setor_origem_id=origem.id,
            setor_destino_id=origem.id,
            itens=[{"produto_id": prod.id, "quantidade": 1}],
        )


def test_receber_sem_divergencia(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 40}],
    )
    item = t.itens[0]
    ts.receber(t, recebimentos={item.id: {"quantidade_recebida": 40}})

    assert t.status == RECEBIDA
    so = _saldo(prod.id, origem.id)
    sd = _saldo(prod.id, destino.id)
    assert so.quantidade == Decimal("60.000")  # 100 - 40
    assert so.quantidade_em_transito == Decimal("0.000")
    assert sd.quantidade == Decimal("40.000")  # entrou no destino
    # Invariante: trânsito não conta nos dois lados.
    assert so.disponivel == Decimal("60.000")


def test_receber_com_divergencia_falta(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 50}],
    )
    item = t.itens[0]
    # Chegaram só 45.
    ts.receber(t, recebimentos={item.id: {"quantidade_recebida": 45, "motivo": "5 avariadas"}})

    assert t.status == RECEBIDA_COM_DIVERGENCIA
    so = _saldo(prod.id, origem.id)
    sd = _saldo(prod.id, destino.id)
    assert sd.quantidade == Decimal("45.000")
    assert so.quantidade == Decimal("55.000")  # 100 - 45 recebidos
    # As 5 faltantes permanecem reservadas em trânsito até correção.
    assert so.quantidade_em_transito == Decimal("5.000")
    assert db.session.refresh(item) or item.divergencia is True


def test_corrigir_estorna_pendente(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 50}],
    )
    item = t.itens[0]
    ts.receber(t, recebimentos={item.id: {"quantidade_recebida": 45}})
    ts.corrigir(t, observacao="Erro de contagem na saída")

    assert t.status == CORRIGIDA
    so = _saldo(prod.id, origem.id)
    # As 5 voltam a ficar disponíveis na origem (estorno da reserva).
    assert so.quantidade_em_transito == Decimal("0.000")
    assert so.disponivel == so.quantidade  # nada mais reservado
    assert so.quantidade == Decimal("55.000")


def test_cancelar_estorna_reserva(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 30}],
    )
    ts.cancelar(t)
    assert t.status == CANCELADA
    so = _saldo(prod.id, origem.id)
    assert so.quantidade_em_transito == Decimal("0.000")
    assert so.disponivel == Decimal("100.000")


def test_nao_recebe_se_nao_enviada(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 10}],
    )
    ts.cancelar(t)
    with pytest.raises(ErroTransferencia):
        ts.receber(t, recebimentos={t.itens[0].id: {"quantidade_recebida": 10}})


def test_corrigir_so_com_divergencia(cenario):
    org, origem, destino, prod = cenario.values()
    t = ts.enviar(
        org.id,
        setor_origem_id=origem.id,
        setor_destino_id=destino.id,
        itens=[{"produto_id": prod.id, "quantidade": 10}],
    )
    ts.receber(t, recebimentos={t.itens[0].id: {"quantidade_recebida": 10}})
    with pytest.raises(ErroTransferencia):
        ts.corrigir(t)
