"""Escopo de setor: onde o usuário pode atuar e o que pode visualizar.

- **Operacional:** setores onde o usuário tem papel (e suas subárvores) — pode agir.
- **Visível:** operacional + setores liberados por regras de visibilidade (§8.3),
  estes em **somente leitura**.

Nunca confiar em parâmetro de URL para escolher setor: validar contra estes conjuntos.
"""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models.setor import Setor
from app.models.usuario import Usuario
from app.models.visibilidade import RegraVisibilidade


def _todos_ids_org(organizacao_id: int) -> set[int]:
    return set(db.session.scalars(select(Setor.id).where(Setor.organizacao_id == organizacao_id)))


def _subarvore_ids(setor_ids: set[int], organizacao_id: int) -> set[int]:
    """Expande um conjunto de setores para incluir todas as subárvores."""
    if not setor_ids:
        return set()
    bases = db.session.scalars(
        select(Setor).where(Setor.id.in_(setor_ids), Setor.organizacao_id == organizacao_id)
    ).all()
    resultado: set[int] = set()
    for base in bases:
        resultado.add(base.id)
        prefixo = f"{base.path}/"
        filhos = db.session.scalars(
            select(Setor.id).where(
                Setor.organizacao_id == organizacao_id, Setor.path.like(f"{prefixo}%")
            )
        )
        resultado.update(filhos)
    return resultado


def setores_operacionais_ids(usuario: Usuario) -> set[int]:
    """IDs de setores onde o usuário pode atuar (papéis + subárvores)."""
    if usuario.superadmin:
        return _todos_ids_org(usuario.organizacao_id)

    # Papel com escopo de organização (setor_id None) => toda a organização.
    tem_escopo_org = any(a.setor_id is None for a in usuario.papeis)
    if tem_escopo_org:
        return _todos_ids_org(usuario.organizacao_id)

    bases = {a.setor_id for a in usuario.papeis if a.setor_id is not None}
    return _subarvore_ids(bases, usuario.organizacao_id)


def setores_visiveis_ids(usuario: Usuario) -> set[int]:
    """IDs de setores que o usuário pode visualizar (operacional + visibilidade)."""
    visiveis = setores_operacionais_ids(usuario)
    if usuario.superadmin or any(a.setor_id is None for a in usuario.papeis):
        return visiveis  # já abrange a organização inteira

    regras = db.session.scalars(
        select(RegraVisibilidade).where(
            RegraVisibilidade.organizacao_id == usuario.organizacao_id,
            RegraVisibilidade.setor_observador_id.in_(visiveis or {0}),
        )
    ).all()

    alvos_diretos = {r.setor_alvo_id for r in regras if not r.inclui_subarvore}
    alvos_subarvore = {r.setor_alvo_id for r in regras if r.inclui_subarvore}
    visiveis |= alvos_diretos
    visiveis |= _subarvore_ids(alvos_subarvore, usuario.organizacao_id)
    return visiveis


def pode_ver_setor(usuario: Usuario, setor_id: int) -> bool:
    return setor_id in setores_visiveis_ids(usuario)


def pode_atuar_no_setor(usuario: Usuario, setor_id: int) -> bool:
    return setor_id in setores_operacionais_ids(usuario)
