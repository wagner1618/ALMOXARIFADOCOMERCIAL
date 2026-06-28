"""Testes do serviço de empréstimos (§7.5): consumível e durável, devolução e vencidos."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.ativo import EM_ESTOQUE, EMPRESTADO, Ativo
from app.models.movimentacao import DEVOLUCAO, EMPRESTIMO, Movimentacao
from app.models.setor import Setor
from app.services import emprestimo_service, estoque_service, produto_service
from app.services.emprestimo_service import ErroEmprestimo


@pytest.fixture()
def base(org):
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    prod = produto_service.criar_produto(org.id, nome="Cabo HDMI", unidade="UN", commit=False)
    db.session.flush()
    estoque_service.entrada(
        org.id, produto_id=prod.id, setor_id=setor.id, quantidade=10, commit=False
    )
    ativo = Ativo(
        organizacao_id=org.id, nome="Projetor", status_ciclo=EM_ESTOQUE, setor_atual_id=setor.id
    )
    db.session.add(ativo)
    db.session.commit()
    return {"org": org, "setor": setor, "prod": prod, "ativo": ativo}


def test_emprestar_consumivel_subtrai_saldo(base):
    c = base
    emp = emprestimo_service.emprestar(
        c["org"].id, produto_id=c["prod"].id, setor_id=c["setor"].id,
        quantidade="3", destinatario="João", commit=False,
    )
    db.session.flush()
    assert emp.status == "ATIVO"
    saldo = estoque_service.obter_saldo(c["prod"].id, c["setor"].id)
    assert saldo.quantidade == Decimal("7.000")  # 10 - 3
    assert db.session.query(Movimentacao).filter_by(tipo=EMPRESTIMO).count() == 1


def test_devolucao_parcial_e_total(base):
    c = base
    emp = emprestimo_service.emprestar(
        c["org"].id, produto_id=c["prod"].id, setor_id=c["setor"].id,
        quantidade="4", destinatario="Maria", commit=False,
    )
    db.session.flush()
    emprestimo_service.devolver(emp, quantidade="1", commit=False)
    assert emp.status == "PARCIAL"
    assert emp.quantidade_pendente == Decimal("3.000")
    saldo = estoque_service.obter_saldo(c["prod"].id, c["setor"].id)
    assert saldo.quantidade == Decimal("7.000")  # 10 - 4 + 1

    emprestimo_service.devolver(emp, commit=False)  # devolve o restante
    assert emp.status == "DEVOLVIDO"
    assert emp.data_devolucao is not None
    assert estoque_service.obter_saldo(c["prod"].id, c["setor"].id).quantidade == Decimal("10.000")


def test_emprestar_durable_muda_status_ciclo(base):
    c = base
    emp = emprestimo_service.emprestar(
        c["org"].id, ativo_id=c["ativo"].id, setor_id=c["setor"].id,
        destinatario="TI", commit=False,
    )
    db.session.flush()
    db.session.refresh(c["ativo"])
    assert c["ativo"].status_ciclo == EMPRESTADO
    assert emp.quantidade == Decimal("1")

    emprestimo_service.devolver(emp, commit=False)
    db.session.flush()
    db.session.refresh(c["ativo"])
    assert c["ativo"].status_ciclo == EM_ESTOQUE
    assert emp.status == "DEVOLVIDO"
    assert db.session.query(Movimentacao).filter_by(tipo=DEVOLUCAO).count() == 1


def test_saldo_insuficiente_falha(base):
    c = base
    with pytest.raises(ErroEmprestimo):
        emprestimo_service.emprestar(
            c["org"].id, produto_id=c["prod"].id, setor_id=c["setor"].id,
            quantidade="999", destinatario="X", commit=False,
        )


def test_ativo_ja_emprestado_falha(base):
    c = base
    emprestimo_service.emprestar(
        c["org"].id, ativo_id=c["ativo"].id, setor_id=c["setor"].id, destinatario="A", commit=False
    )
    db.session.flush()
    with pytest.raises(ErroEmprestimo):
        emprestimo_service.emprestar(
            c["org"].id, ativo_id=c["ativo"].id, setor_id=c["setor"].id, destinatario="B",
            commit=False,
        )


def test_vencido_derivado(base):
    c = base
    emp = emprestimo_service.emprestar(
        c["org"].id, produto_id=c["prod"].id, setor_id=c["setor"].id, quantidade="1",
        destinatario="Z", data_prevista=date.today() - timedelta(days=1), commit=False,
    )
    assert emp.vencido is True
    assert emp.rotulo_status == "Vencido"


def test_exige_produto_ou_ativo(base):
    c = base
    with pytest.raises(ErroEmprestimo):
        emprestimo_service.emprestar(c["org"].id, setor_id=c["setor"].id, destinatario="X")
