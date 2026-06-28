"""Testes do serviço de setores: path, mover subárvore, ciclos, inativação."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.setor import Setor
from app.services import setor_service
from app.services.setor_service import ErroSetor


@pytest.fixture()
def org_arvore(app):
    """Cria uma árvore: Central > (A > A1), (B)."""
    from app.services import setup

    organizacao = setup.criar_organizacao("Org Setores", slug="setores")
    central = (
        db.session.query(Setor).filter_by(organizacao_id=organizacao.id, codigo="CENTRAL").one()
    )
    a = setor_service.criar_setor(organizacao.id, nome="A", setor_pai_id=central.id)
    a1 = setor_service.criar_setor(organizacao.id, nome="A1", setor_pai_id=a.id)
    b = setor_service.criar_setor(organizacao.id, nome="B", setor_pai_id=central.id)
    return {"org": organizacao, "central": central, "a": a, "a1": a1, "b": b}


def test_path_e_nivel(org_arvore):
    central, a, a1 = org_arvore["central"], org_arvore["a"], org_arvore["a1"]
    assert a.path == f"{central.id}/{a.id}"
    assert a.nivel == 2
    assert a1.path == f"{central.id}/{a.id}/{a1.id}"
    assert a1.nivel == 3


def test_descendentes(org_arvore):
    central = org_arvore["central"]
    ids = setor_service.ids_subarvore(central)
    esperado = {org_arvore[k].id for k in ("central", "a", "a1", "b")}
    assert ids == esperado


def test_mover_subarvore_recalcula_paths(org_arvore):
    a, a1, b = org_arvore["a"], org_arvore["a1"], org_arvore["b"]
    # Move A (com A1) para baixo de B.
    setor_service.mover_setor(a, b.id)
    db.session.refresh(a)
    db.session.refresh(a1)
    assert a.setor_pai_id == b.id
    assert a.path == f"{b.path}/{a.id}"
    assert a1.path == f"{b.path}/{a.id}/{a1.id}"
    assert a1.nivel == 4


def test_mover_para_subarvore_propria_falha(org_arvore):
    a, a1 = org_arvore["a"], org_arvore["a1"]
    with pytest.raises(ErroSetor):
        setor_service.mover_setor(a, a1.id)


def test_setor_nao_pode_ser_pai_de_si(org_arvore):
    a = org_arvore["a"]
    with pytest.raises(ErroSetor):
        setor_service.mover_setor(a, a.id)


def test_inativar_em_cascata(org_arvore):
    a = org_arvore["a"]
    setor_service.inativar_setor(a, em_cascata=True)
    db.session.refresh(a)
    db.session.refresh(org_arvore["a1"])
    assert a.ativo is False
    assert org_arvore["a1"].ativo is False
    # B não é afetado.
    db.session.refresh(org_arvore["b"])
    assert org_arvore["b"].ativo is True
