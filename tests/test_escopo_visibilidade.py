"""Testes de escopo de setor e regras de visibilidade (§8.3)."""

from __future__ import annotations

import pytest

from app.extensions import db
from app.models.rbac import Papel, UsuarioPapel
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.models.visibilidade import RegraVisibilidade
from app.security import escopo
from app.services import setor_service, setup


@pytest.fixture()
def cenario(app):
    """Org com Central > A > A1 e Central > B; um operador com escopo no setor A."""
    org = setup.criar_organizacao("Org Escopo", slug="escopo", commit=False)
    db.session.commit()
    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    a = setor_service.criar_setor(org.id, nome="A", setor_pai_id=central.id)
    a1 = setor_service.criar_setor(org.id, nome="A1", setor_pai_id=a.id)
    b = setor_service.criar_setor(org.id, nome="B", setor_pai_id=central.id)

    operador = Usuario(
        organizacao_id=org.id,
        nome="Op",
        email="op@e.local",
        username="op",
        deve_trocar_senha=False,
    )
    operador.definir_senha("Senha@12345")
    db.session.add(operador)
    db.session.flush()
    papel = db.session.query(Papel).filter_by(organizacao_id=org.id, nome="Operador").one()
    db.session.add(UsuarioPapel(usuario_id=operador.id, papel_id=papel.id, setor_id=a.id))
    db.session.commit()
    return {"org": org, "central": central, "a": a, "a1": a1, "b": b, "operador": operador}


def test_escopo_operacional_inclui_subarvore(cenario):
    op = cenario["operador"]
    ids = escopo.setores_operacionais_ids(op)
    assert ids == {cenario["a"].id, cenario["a1"].id}
    # Não enxerga B nem Central operacionalmente.
    assert cenario["b"].id not in ids
    assert cenario["central"].id not in ids


def test_visibilidade_padrao_igual_operacional(cenario):
    op = cenario["operador"]
    assert escopo.setores_visiveis_ids(op) == escopo.setores_operacionais_ids(op)


def test_regra_visibilidade_amplia_leitura(cenario):
    op, org, a, b = cenario["operador"], cenario["org"], cenario["a"], cenario["b"]
    db.session.add(
        RegraVisibilidade(
            organizacao_id=org.id,
            setor_observador_id=a.id,
            setor_alvo_id=b.id,
            inclui_subarvore=False,
        )
    )
    db.session.commit()
    visiveis = escopo.setores_visiveis_ids(op)
    assert b.id in visiveis
    # Mas continua não sendo operacional (somente leitura).
    assert b.id not in escopo.setores_operacionais_ids(op)


def test_admin_escopo_org_ve_tudo(cenario):
    # Admin tem papel com escopo de organização (setor_id None) => vê tudo.
    org = cenario["org"]
    novo = setup.criar_usuario_admin(
        org,
        nome="Adm",
        email="adm@e.local",
        username="adm",
        senha="Senha@12345",
        deve_trocar_senha=False,
    )
    ids = escopo.setores_operacionais_ids(novo)
    todos = {cenario[k].id for k in ("central", "a", "a1", "b")}
    assert ids == todos
