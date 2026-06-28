"""Serviços de provisionamento: permissões, papéis padrão, organização e admin.

Todas as funções são **idempotentes** — podem rodar várias vezes sem duplicar.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from app.extensions import db
from app.models.organizacao import Organizacao
from app.models.rbac import Papel, Permissao
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.security.permissions import PAPEIS_PADRAO, PERMISSOES


def _slugify(texto: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", texto.strip().lower()).strip("-")
    return base or "org"


def sincronizar_permissoes() -> int:
    """Garante que toda permissão do catálogo exista na tabela. Retorna nº criadas."""
    existentes = {p.chave for p in db.session.scalars(select(Permissao)).all()}
    criadas = 0
    for chave, (categoria, descricao) in PERMISSOES.items():
        if chave not in existentes:
            db.session.add(Permissao(chave=chave, categoria=categoria, descricao=descricao))
            criadas += 1
        else:
            perm = db.session.scalar(select(Permissao).where(Permissao.chave == chave))
            if perm:
                perm.categoria, perm.descricao = categoria, descricao
    db.session.flush()
    return criadas


def criar_papeis_padrao(org: Organizacao) -> list[Papel]:
    """Cria (ou atualiza) os papéis-semente da organização."""
    perms_por_chave = {p.chave: p for p in db.session.scalars(select(Permissao)).all()}
    papeis: list[Papel] = []
    for nome, (nivel, descricao, chaves) in PAPEIS_PADRAO.items():
        papel = db.session.scalar(
            select(Papel).where(Papel.organizacao_id == org.id, Papel.nome == nome)
        )
        if papel is None:
            papel = Papel(organizacao_id=org.id, nome=nome, sistema=True)
            db.session.add(papel)
        papel.nivel = nivel
        papel.descricao = descricao
        papel.permissoes = [perms_por_chave[c] for c in chaves if c in perms_por_chave]
        papeis.append(papel)
    db.session.flush()
    return papeis


def criar_modelos_documento_padrao(org: Organizacao) -> list:
    """Cria (idempotente) um ModeloDocumento editável por tipo, com o template base."""
    from app.models.documento import ROTULO_DOCUMENTO, TIPOS_DOCUMENTO, ModeloDocumento
    from app.services.documento_service import MODELO_PADRAO

    modelos = []
    for tipo in TIPOS_DOCUMENTO:
        existente = db.session.scalar(
            select(ModeloDocumento).where(
                ModeloDocumento.organizacao_id == org.id, ModeloDocumento.tipo == tipo
            )
        )
        if existente is None:
            existente = ModeloDocumento(
                organizacao_id=org.id,
                tipo=tipo,
                nome=f"Modelo padrão — {ROTULO_DOCUMENTO[tipo]}",
                conteudo_html=MODELO_PADRAO,
            )
            db.session.add(existente)
        modelos.append(existente)
    db.session.flush()
    return modelos


def criar_organizacao(
    nome: str, *, slug: str | None = None, plano: str = "basico", commit: bool = True
) -> Organizacao:
    """Cria uma organização com permissões sincronizadas e papéis padrão."""
    slug = _slugify(slug or nome)
    if db.session.scalar(select(Organizacao).where(Organizacao.slug == slug)):
        raise ValueError(f"Já existe uma organização com o slug {slug!r}.")

    sincronizar_permissoes()
    org = Organizacao(nome=nome, slug=slug, plano=plano)
    db.session.add(org)
    db.session.flush()

    # Setor principal raiz (central/órgão).
    principal = Setor(organizacao_id=org.id, nome="Almoxarifado Central", codigo="CENTRAL")
    db.session.add(principal)
    db.session.flush()
    principal.atualizar_path()

    criar_papeis_padrao(org)
    criar_modelos_documento_padrao(org)
    if commit:
        db.session.commit()
    return org


def criar_usuario_admin(
    org: Organizacao,
    *,
    nome: str,
    email: str,
    username: str,
    senha: str,
    deve_trocar_senha: bool = True,
    commit: bool = True,
) -> Usuario:
    """Cria um usuário com o papel 'Administrador da Organização' (escopo org)."""
    from app.models.rbac import UsuarioPapel

    if db.session.scalar(
        select(Usuario).where(
            Usuario.organizacao_id == org.id,
            (Usuario.email == email) | (Usuario.username == username),
        )
    ):
        raise ValueError("Já existe usuário com este e-mail ou username na organização.")

    usuario = Usuario(
        organizacao_id=org.id,
        nome=nome,
        email=email.lower(),
        username=username.lower(),
        cargo="Administrador",
        deve_trocar_senha=deve_trocar_senha,
    )
    usuario.definir_senha(senha)
    db.session.add(usuario)
    db.session.flush()

    papel_admin = db.session.scalar(
        select(Papel).where(
            Papel.organizacao_id == org.id, Papel.nome == "Administrador da Organização"
        )
    )
    if papel_admin:
        db.session.add(UsuarioPapel(usuario_id=usuario.id, papel_id=papel_admin.id, setor_id=None))

    if commit:
        db.session.commit()
    return usuario


def criar_superadmin(
    *, nome: str, email: str, username: str, senha: str, commit: bool = True
) -> Usuario:
    """Cria/garante a organização-plataforma e um usuário superadmin nela."""
    org = db.session.scalar(select(Organizacao).where(Organizacao.slug == "plataforma"))
    if org is None:
        org = criar_organizacao("Plataforma", slug="plataforma", plano="enterprise", commit=False)

    existente = db.session.scalar(select(Usuario).where(Usuario.username == username.lower()))
    if existente:
        existente.superadmin = True
        if commit:
            db.session.commit()
        return existente

    usuario = Usuario(
        organizacao_id=org.id,
        nome=nome,
        email=email.lower(),
        username=username.lower(),
        cargo="Operador da Plataforma",
        superadmin=True,
        deve_trocar_senha=False,
    )
    usuario.definir_senha(senha)
    db.session.add(usuario)
    if commit:
        db.session.commit()
    return usuario
