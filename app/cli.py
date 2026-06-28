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
    db.session.commit()

    click.secho("✓ Dados de demonstração criados.", fg="green")
    click.echo("  Organização: Organização Demonstração (slug=demo)")
    click.echo(f"  Login: admin / {senha}")
