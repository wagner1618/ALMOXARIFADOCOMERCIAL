"""Testes de RBAC, permissões e isolamento multi-tenant."""

from __future__ import annotations

from app.extensions import db
from app.models.usuario import Usuario
from app.security.permissions import PERMISSOES
from app.services import setup


def test_admin_tem_todas_permissoes(app, org):
    admin = db.session.query(Usuario).filter_by(username="admin").one()
    # O papel admin recebe o catálogo inteiro.
    for chave in PERMISSOES:
        assert admin.tem_permissao(chave), f"admin deveria ter {chave}"


def test_permissao_negada_para_chave_inexistente(app, org):
    admin = db.session.query(Usuario).filter_by(username="admin").one()
    assert not admin.tem_permissao("inexistente.acao")


def test_superadmin_tem_curinga(app):
    su = setup.criar_superadmin(
        nome="Root", email="root@plataforma.local", username="root", senha="Root@12345"
    )
    assert su.tem_permissao("qualquer.coisa")
    assert su.permissoes == {"*"}


def test_isolamento_entre_organizacoes(app):
    org_a = setup.criar_organizacao("Org A", slug="a", commit=False)
    org_b = setup.criar_organizacao("Org B", slug="b", commit=False)
    db.session.commit()

    setup.criar_usuario_admin(
        org_a,
        nome="A",
        email="a@a.local",
        username="ua",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    setup.criar_usuario_admin(
        org_b,
        nome="B",
        email="b@b.local",
        username="ub",
        senha="Senha@12345",
        deve_trocar_senha=False,
        commit=False,
    )
    db.session.commit()

    usuarios_a = db.session.query(Usuario).filter_by(organizacao_id=org_a.id).all()
    assert {u.username for u in usuarios_a} == {"ua"}
    # Mesmo username/email pode coexistir em organizações diferentes.
    assert org_a.id != org_b.id


def test_setor_path_materializado(app):
    org = setup.criar_organizacao("Org Árvore", slug="arvore")
    from app.models.setor import Setor

    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    assert central.path == str(central.id)
    assert central.nivel == 1

    filho = Setor(organizacao_id=org.id, nome="Filho", codigo="F1", setor_pai_id=central.id)
    db.session.add(filho)
    db.session.flush()
    filho.atualizar_path()
    assert filho.path == f"{central.id}/{filho.id}"
    assert filho.nivel == 2


def test_forcar_troca_senha_bloqueia(client, app):
    org = setup.criar_organizacao("Org Troca", slug="troca", commit=False)
    setup.criar_usuario_admin(
        org,
        nome="Novo",
        email="novo@t.local",
        username="novo",
        senha="Senha@12345",
        deve_trocar_senha=True,
        commit=False,
    )
    db.session.commit()

    client.post("/login", data={"identificador": "novo", "senha": "Senha@12345"})
    # Tentar acessar o dashboard deve redirecionar para troca de senha.
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/trocar-senha" in resp.headers["Location"]
