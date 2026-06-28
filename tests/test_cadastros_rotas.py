"""Testes de rota dos cadastros (setores, categorias, localizações, visibilidade)."""

from __future__ import annotations

from app.extensions import db
from app.models.categoria import Categoria
from app.models.setor import Setor
from app.models.visibilidade import RegraVisibilidade
from tests.conftest import login


def test_listar_setores_exige_login(client, org):
    resp = client.get("/setores/", follow_redirects=False)
    assert resp.status_code == 302


def test_criar_setor_via_rota(client, org):
    login(client)
    resp = client.post(
        "/setores/novo",
        data={"nome": "Compras", "codigo": "CMP", "setor_pai_id": 0, "submit": "Salvar"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    setor = db.session.query(Setor).filter_by(organizacao_id=org.id, nome="Compras").first()
    assert setor is not None
    assert setor.path == str(setor.id)  # raiz


def test_criar_subsetor_e_arvore(client, org):
    login(client)
    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    client.post(
        "/setores/novo",
        data={"nome": "Almox A", "setor_pai_id": central.id, "submit": "Salvar"},
        follow_redirects=True,
    )
    filho = db.session.query(Setor).filter_by(organizacao_id=org.id, nome="Almox A").one()
    assert filho.setor_pai_id == central.id
    assert filho.nivel == 2

    # A árvore deve listar ambos.
    resp = client.get("/setores/")
    corpo = resp.get_data(as_text=True)
    assert "Almox A" in corpo
    assert "Almoxarifado Central" in corpo


def test_criar_categoria_via_rota(client, org):
    login(client)
    resp = client.post(
        "/categorias/nova",
        data={"nome": "Informática", "ativo": "y", "submit": "Salvar"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert (
        db.session.query(Categoria).filter_by(organizacao_id=org.id, nome="Informática").first()
        is not None
    )


def test_categoria_duplicada_bloqueada(client, org):
    login(client)
    dados = {"nome": "Limpeza", "ativo": "y", "submit": "Salvar"}
    client.post("/categorias/nova", data=dados, follow_redirects=True)
    client.post("/categorias/nova", data=dados, follow_redirects=True)
    qtd = db.session.query(Categoria).filter_by(organizacao_id=org.id, nome="Limpeza").count()
    assert qtd == 1


def test_adicionar_regra_visibilidade(client, org):
    login(client)
    central = db.session.query(Setor).filter_by(organizacao_id=org.id, codigo="CENTRAL").one()
    # cria um segundo setor
    client.post(
        "/setores/novo",
        data={"nome": "Setor X", "setor_pai_id": 0, "submit": "Salvar"},
        follow_redirects=True,
    )
    sx = db.session.query(Setor).filter_by(organizacao_id=org.id, nome="Setor X").one()
    resp = client.post(
        "/setores/visibilidade",
        data={
            "setor_observador_id": sx.id,
            "setor_alvo_id": central.id,
            "inclui_subarvore": "y",
            "submit": "Adicionar regra",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert (
        db.session.query(RegraVisibilidade)
        .filter_by(organizacao_id=org.id, setor_observador_id=sx.id, setor_alvo_id=central.id)
        .first()
        is not None
    )


def test_consulta_sem_permissao_recebe_403(client, org):
    """Usuário só-leitura não pode acessar a gestão de setores."""
    from app.models.rbac import Papel, UsuarioPapel
    from app.models.usuario import Usuario

    u = Usuario(
        organizacao_id=org.id,
        nome="Leitor",
        email="leitor@t.local",
        username="leitor",
        deve_trocar_senha=False,
    )
    u.definir_senha("Senha@12345")
    db.session.add(u)
    db.session.flush()
    papel = db.session.query(Papel).filter_by(organizacao_id=org.id, nome="Consulta").one()
    db.session.add(UsuarioPapel(usuario_id=u.id, papel_id=papel.id, setor_id=None))
    db.session.commit()

    login(client, identificador="leitor")
    resp = client.get("/setores/")
    assert resp.status_code == 403
