"""Testes do ciclo de vida do ativo (patrimônio)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.ativo import (
    BAIXADO,
    BOM,
    EM_ESTOQUE,
    EM_MANUTENCAO,
    EM_USO,
    INSERVIVEL,
)
from app.services import ativo_service, setor_service, setup
from app.services.ativo_service import ErroAtivo


@pytest.fixture()
def cenario(app):
    org = setup.criar_organizacao("Org A", slug="a")
    from app.models.setor import Setor

    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    sala = setor_service.criar_setor(org.id, nome="Sala 1", setor_pai_id=central.id)
    return {"org": org, "central": central, "sala": sala}


def _criar(org_id, central_id, **kw):
    dados = {"nome": "Notebook", "estado_conservacao": BOM, "setor_atual_id": central_id}
    dados.update(kw)
    return ativo_service.criar_ativo(org_id, dados=dados)


def test_criar_em_estoque(cenario):
    a = _criar(cenario["org"].id, cenario["central"].id, tombamento="TOMB-1")
    assert a.status_ciclo == EM_ESTOQUE
    assert a.tombamento == "TOMB-1"


def test_tombamento_unico(cenario):
    org, central = cenario["org"], cenario["central"]
    _criar(org.id, central.id, tombamento="DUP")
    with pytest.raises(ErroAtivo):
        _criar(org.id, central.id, tombamento="DUP")


def test_serie_unica(cenario):
    org, central = cenario["org"], cenario["central"]
    _criar(org.id, central.id, numero_serie="SN-1")
    with pytest.raises(ErroAtivo):
        _criar(org.id, central.id, numero_serie="SN-1")


def test_destinar_e_retornar(cenario):
    org, central, sala = cenario.values()
    a = _criar(org.id, central.id, tombamento="T1")
    ativo_service.destinar(a, setor_id=sala.id)
    assert a.status_ciclo == EM_USO
    assert a.setor_atual_id == sala.id
    ativo_service.retornar_estoque(a)
    assert a.status_ciclo == EM_ESTOQUE
    assert a.usuario_responsavel_id is None


def test_inservivel_nao_destina(cenario):
    org, central, sala = cenario.values()
    a = _criar(org.id, central.id, estado_conservacao=INSERVIVEL)
    with pytest.raises(ErroAtivo):
        ativo_service.destinar(a, setor_id=sala.id)


def test_manutencao(cenario):
    org, central, _sala = cenario.values()
    a = _criar(org.id, central.id)
    ativo_service.enviar_manutencao(a)
    assert a.status_ciclo == EM_MANUTENCAO
    ativo_service.concluir_manutencao(a, novo_estado="REGULAR")
    assert a.status_ciclo == EM_ESTOQUE
    assert a.estado_conservacao == "REGULAR"


def test_baixa_exige_justificativa_e_estoque(cenario):
    org, central, sala = cenario.values()
    a = _criar(org.id, central.id)
    with pytest.raises(ErroAtivo):
        ativo_service.baixar(a, justificativa="")
    # Em uso não pode baixar.
    ativo_service.destinar(a, setor_id=sala.id)
    with pytest.raises(ErroAtivo):
        ativo_service.baixar(a, justificativa="Sucateado")
    # De volta ao estoque, pode.
    ativo_service.retornar_estoque(a)
    ativo_service.baixar(a, justificativa="Sucateado")
    assert a.status_ciclo == BAIXADO
    assert a.ativo is False


def test_baixado_nao_movimenta(cenario):
    org, central, sala = cenario.values()
    a = _criar(org.id, central.id)
    ativo_service.baixar(a, justificativa="Fim de vida")
    with pytest.raises(ErroAtivo):
        ativo_service.transferir(a, setor_id=sala.id)


def test_recertificacao_agenda_proxima(cenario):
    org, central, _sala = cenario.values()
    a = _criar(org.id, central.id)
    ativo_service.recertificar(a, estado_conservacao="DEFASADO", meses_proxima=12)
    assert a.estado_conservacao == "DEFASADO"
    assert a.ultima_revisao_em == date.today()
    assert a.proxima_revisao_em > date.today()


def test_recertificar_inservivel_em_uso_volta_estoque(cenario):
    org, central, sala = cenario.values()
    a = _criar(org.id, central.id)
    ativo_service.destinar(a, setor_id=sala.id)
    ativo_service.recertificar(a, estado_conservacao=INSERVIVEL)
    assert a.status_ciclo == EM_ESTOQUE
    assert a.usuario_responsavel_id is None


def test_depreciacao_linear(cenario):
    org, central, _sala = cenario.values()
    inicio = date.today() - timedelta(days=365)  # ~12 meses
    a = _criar(
        org.id,
        central.id,
        valor_aquisicao=Decimal("1200.00"),
        valor_residual=Decimal("0.00"),
        vida_util_meses=24,
        data_aquisicao=inicio,
    )
    # ~12 de 24 meses => ~metade depreciada.
    vc = a.valor_contabil
    assert Decimal("500.00") <= vc <= Decimal("700.00")


def test_revisao_vencida_flag(cenario):
    org, central, _sala = cenario.values()
    a = _criar(org.id, central.id)
    a.proxima_revisao_em = date.today() - timedelta(days=1)
    assert a.revisao_vencida is True
