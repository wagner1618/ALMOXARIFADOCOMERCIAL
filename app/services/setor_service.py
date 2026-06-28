"""Serviço de setores: árvore, ``path`` materializado, mover subárvore, inativar."""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import db
from app.models.setor import Setor


class ErroSetor(Exception):
    """Erro de regra de negócio em operações de setor."""


def listar_setores(organizacao_id: int, *, apenas_ativos: bool = False) -> list[Setor]:
    stmt = select(Setor).where(Setor.organizacao_id == organizacao_id)
    if apenas_ativos:
        stmt = stmt.where(Setor.ativo.is_(True))
    # Ordena por path para já sair em ordem de árvore (pais antes dos filhos).
    return list(db.session.scalars(stmt.order_by(Setor.path)))


def arvore(organizacao_id: int, *, apenas_ativos: bool = False) -> list[dict]:
    """Lista de setores anotada com profundidade (nivel-1) para indentação."""
    setores = listar_setores(organizacao_id, apenas_ativos=apenas_ativos)
    return [{"setor": s, "profundidade": s.nivel - 1} for s in setores]


def descendentes(setor: Setor, *, incluir_self: bool = False) -> list[Setor]:
    """Todos os setores na subárvore (via prefixo de ``path``)."""
    prefixo = f"{setor.path}/"
    stmt = select(Setor).where(
        Setor.organizacao_id == setor.organizacao_id, Setor.path.like(f"{prefixo}%")
    )
    filhos = list(db.session.scalars(stmt.order_by(Setor.path)))
    return [setor, *filhos] if incluir_self else filhos


def ids_subarvore(setor: Setor) -> set[int]:
    return {s.id for s in descendentes(setor, incluir_self=True)}


def criar_setor(
    organizacao_id: int,
    *,
    nome: str,
    codigo: str | None = None,
    setor_pai_id: int | None = None,
    poder_compra: bool = False,
    centro_custo: str | None = None,
    orcamento_anual: float | None = None,
    permite_visualizacao_externa: bool = False,
    commit: bool = True,
) -> Setor:
    pai = _carregar_pai(organizacao_id, setor_pai_id)
    setor = Setor(
        organizacao_id=organizacao_id,
        nome=nome.strip(),
        codigo=(codigo or None),
        setor_pai_id=setor_pai_id,
        poder_compra=poder_compra,
        centro_custo=centro_custo or None,
        orcamento_anual=orcamento_anual,
        permite_visualizacao_externa=permite_visualizacao_externa,
    )
    setor.pai = pai
    db.session.add(setor)
    db.session.flush()  # garante id para o path
    setor.atualizar_path()
    if commit:
        db.session.commit()
    return setor


def atualizar_setor(setor: Setor, *, dados: dict, commit: bool = True) -> Setor:
    """Atualiza campos simples e, se o pai mudou, move a subárvore."""
    novo_pai_id = dados.get("setor_pai_id", setor.setor_pai_id)
    for campo in (
        "nome",
        "codigo",
        "poder_compra",
        "centro_custo",
        "orcamento_anual",
        "permite_visualizacao_externa",
        "ativo",
    ):
        if campo in dados:
            setattr(setor, campo, dados[campo])

    if novo_pai_id != setor.setor_pai_id:
        mover_setor(setor, novo_pai_id, commit=False)

    if commit:
        db.session.commit()
    return setor


def mover_setor(setor: Setor, novo_pai_id: int | None, *, commit: bool = True) -> Setor:
    """Reparenta o setor e recalcula o ``path``/``nivel`` de toda a subárvore."""
    if novo_pai_id == setor.id:
        raise ErroSetor("Um setor não pode ser pai de si mesmo.")

    novo_pai = _carregar_pai(setor.organizacao_id, novo_pai_id)
    if novo_pai is not None and (
        novo_pai.path == setor.path or novo_pai.path.startswith(f"{setor.path}/")
    ):
        raise ErroSetor("Não é possível mover um setor para dentro da própria subárvore.")

    afetados = descendentes(setor, incluir_self=True)
    path_antigo = setor.path
    path_novo = str(setor.id) if novo_pai is None else f"{novo_pai.path}/{setor.id}"

    for s in afetados:
        s.path = path_novo + s.path[len(path_antigo) :]
        s.nivel = s.path.count("/") + 1

    setor.setor_pai_id = novo_pai_id
    db.session.flush()
    if commit:
        db.session.commit()
    return setor


def inativar_setor(setor: Setor, *, em_cascata: bool = False, commit: bool = True) -> None:
    """Inativa o setor (soft delete). Histórico nunca é apagado."""
    alvos = descendentes(setor, incluir_self=True) if em_cascata else [setor]
    for s in alvos:
        s.ativo = False
    if commit:
        db.session.commit()


def _carregar_pai(organizacao_id: int, setor_pai_id: int | None) -> Setor | None:
    if setor_pai_id is None:
        return None
    pai = db.session.get(Setor, setor_pai_id)
    if pai is None or pai.organizacao_id != organizacao_id:
        raise ErroSetor("Setor pai inválido para esta organização.")
    return pai
