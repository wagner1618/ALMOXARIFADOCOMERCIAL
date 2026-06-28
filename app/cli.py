"""Comandos de linha de comando: criar-org, criar-admin, seed."""

from __future__ import annotations

import secrets

import click
from flask import Flask
from flask.cli import AppGroup

from app.extensions import db
from app.services import setup

almox_cli = AppGroup("almox", help="Comandos de administração do almoxarifado.")


def register(app: Flask) -> None:
    app.cli.add_command(almox_cli)


@almox_cli.command("sincronizar-permissoes")
def sincronizar_permissoes_cmd() -> None:
    """Sincroniza o catálogo de permissões com o banco."""
    criadas = setup.sincronizar_permissoes()
    db.session.commit()
    click.secho(f"✓ Permissões sincronizadas ({criadas} novas).", fg="green")


@almox_cli.command("criar-org")
@click.option("--nome", prompt="Nome da organização", help="Nome do cliente/tenant.")
@click.option("--slug", default=None, help="Slug único (gerado do nome se omitido).")
@click.option("--plano", default="basico", show_default=True)
def criar_org_cmd(nome: str, slug: str | None, plano: str) -> None:
    """Cria uma nova organização com papéis padrão."""
    org = setup.criar_organizacao(nome, slug=slug, plano=plano)
    click.secho(f"✓ Organização criada: {org.nome} (slug={org.slug}, id={org.id})", fg="green")


@almox_cli.command("criar-admin")
@click.option("--org", "org_slug", prompt="Slug da organização", help="Slug da organização alvo.")
@click.option("--nome", prompt="Nome do administrador")
@click.option("--email", prompt="E-mail")
@click.option("--username", prompt="Usuário (login)")
@click.option("--senha", default=None, help="Senha inicial (gerada se omitida).")
def criar_admin_cmd(org_slug: str, nome: str, email: str, username: str, senha: str | None) -> None:
    """Cria um usuário administrador para uma organização existente."""
    from sqlalchemy import select

    from app.models.organizacao import Organizacao

    org = db.session.scalar(select(Organizacao).where(Organizacao.slug == org_slug))
    if org is None:
        raise click.ClickException(f"Organização com slug {org_slug!r} não encontrada.")

    gerada = senha is None
    senha = senha or secrets.token_urlsafe(9)
    setup.criar_usuario_admin(
        org, nome=nome, email=email, username=username, senha=senha, deve_trocar_senha=True
    )
    click.secho(f"✓ Administrador criado: {username} @ {org.slug}", fg="green")
    if gerada:
        click.secho(f"  Senha inicial: {senha}", fg="yellow")
    click.echo("  (Será exigida a troca de senha no primeiro acesso.)")


@almox_cli.command("criar-superadmin")
@click.option("--nome", prompt="Nome")
@click.option("--email", prompt="E-mail")
@click.option("--username", prompt="Usuário (login)")
@click.option("--senha", default=None, help="Senha (gerada se omitida).")
def criar_superadmin_cmd(nome: str, email: str, username: str, senha: str | None) -> None:
    """Cria o operador da plataforma (superadmin, acima do tenant)."""
    gerada = senha is None
    senha = senha or secrets.token_urlsafe(12)
    setup.criar_superadmin(nome=nome, email=email, username=username, senha=senha)
    click.secho(f"✓ Superadmin criado: {username}", fg="green")
    if gerada:
        click.secho(f"  Senha: {senha}", fg="yellow")


@almox_cli.command("seed")
@click.option("--demo/--no-demo", default=True, help="Cria organização e admin de demonstração.")
def seed_cmd(demo: bool) -> None:
    """Popula dados iniciais (idempotente). Com --demo, cria org/admin de exemplo."""
    from sqlalchemy import select

    from app.models.organizacao import Organizacao

    criadas = setup.sincronizar_permissoes()
    db.session.commit()
    click.secho(f"✓ Permissões sincronizadas ({criadas} novas).", fg="green")

    if not demo:
        return

    if db.session.scalar(select(Organizacao).where(Organizacao.slug == "demo")):
        click.secho("• Organização 'demo' já existe — nada a fazer.", fg="cyan")
        return

    org = setup.criar_organizacao("Organização Demonstração", slug="demo", commit=False)

    # Hierarquia de exemplo (3 níveis) a partir do setor central criado.
    from app.models.setor import Setor

    central = db.session.scalar(
        select(Setor).where(Setor.organizacao_id == org.id, Setor.codigo == "CENTRAL")
    )
    central.poder_compra = True
    central.orcamento_anual = 500000
    secundario = Setor(
        organizacao_id=org.id, nome="Setor Administrativo", codigo="ADM", setor_pai_id=central.id
    )
    db.session.add(secundario)
    db.session.flush()
    secundario.atualizar_path()
    terciario = Setor(
        organizacao_id=org.id, nome="Recepção", codigo="REC", setor_pai_id=secundario.id
    )
    db.session.add(terciario)
    db.session.flush()
    terciario.atualizar_path()

    # Categorias e uma localização de exemplo.
    from app.models.categoria import Categoria
    from app.models.definicao_campo import ENTIDADE_PRODUTO, TIPO_SELECT, TIPO_TEXTO, DefinicaoCampo
    from app.models.localizacao import Localizacao
    from app.models.produto import TIPO_CONSUMIVEL, TIPO_DURAVEL
    from app.services import produto_service

    cats = {}
    for nome_cat in ("Informática", "Material de Escritório", "Limpeza", "Mobiliário"):
        c = Categoria(organizacao_id=org.id, nome=nome_cat)
        db.session.add(c)
        cats[nome_cat] = c
    db.session.add(
        Localizacao(
            organizacao_id=org.id,
            setor_id=central.id,
            nome="Prateleira A1",
            descricao="Estoque principal",
        )
    )
    db.session.flush()

    # Campos customizados de exemplo (categoria Informática).
    db.session.add_all(
        [
            DefinicaoCampo(
                organizacao_id=org.id,
                entidade=ENTIDADE_PRODUTO,
                chave="processador",
                rotulo="Processador",
                tipo=TIPO_TEXTO,
                ordem=1,
                aplica_a_categoria_id=cats["Informática"].id,
            ),
            DefinicaoCampo(
                organizacao_id=org.id,
                entidade=ENTIDADE_PRODUTO,
                chave="condicao",
                rotulo="Condição",
                tipo=TIPO_SELECT,
                opcoes=["Novo", "Usado", "Recondicionado"],
                ordem=2,
            ),
        ]
    )

    senha = "Almox@2026"
    setup.criar_usuario_admin(
        org,
        nome="Administrador Demo",
        email="admin@demo.local",
        username="admin",
        senha=senha,
        deve_trocar_senha=False,
        commit=False,
    )
    db.session.flush()

    # Alguns produtos de exemplo.
    produto_service.criar_produto(
        org.id,
        nome="Papel A4 75g (resma)",
        categoria_id=cats["Material de Escritório"].id,
        unidade="RESMA",
        estoque_minimo=10,
        valor_unitario_referencia=25,
        commit=False,
    )
    produto_service.criar_produto(
        org.id,
        nome="Caneta esferográfica azul",
        categoria_id=cats["Material de Escritório"].id,
        unidade="UN",
        estoque_minimo=50,
        commit=False,
    )
    produto_service.criar_produto(
        org.id,
        nome="Notebook Dell Latitude",
        tipo_controle=TIPO_DURAVEL,
        categoria_id=cats["Informática"].id,
        unidade="UN",
        marca="Dell",
        modelo="Latitude 3540",
        campos={"processador": "Intel i5", "condicao": "Novo"},
        commit=False,
    )
    produto_service.criar_produto(
        org.id,
        nome="Detergente neutro 5L",
        tipo_controle=TIPO_CONSUMIVEL,
        categoria_id=cats["Limpeza"].id,
        unidade="L",
        estoque_minimo=5,
        commit=False,
    )
    db.session.commit()

    click.secho("✓ Dados de demonstração criados.", fg="green")
    click.echo("  Organização: Organização Demonstração (slug=demo)")
    click.echo(f"  Login: admin / {senha}")
