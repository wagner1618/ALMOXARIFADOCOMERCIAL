"""Alertas de estoque: itens em nível mínimo ou zerados."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models.estoque import SaldoEstoque
from app.models.produto import Produto
from app.models.setor import Setor


def itens_em_alerta(organizacao_id: int, *, setor_ids: Iterable[int] | None = None) -> list[dict]:
    """Saldos cujo disponível está <= estoque mínimo (ou zerados).

    Restrito aos setores informados (escopo do usuário), se houver.
    """
    stmt = (
        select(SaldoEstoque, Produto, Setor)
        .join(Produto, SaldoEstoque.produto_id == Produto.id)
        .join(Setor, SaldoEstoque.setor_id == Setor.id)
        .where(SaldoEstoque.organizacao_id == organizacao_id, Produto.ativo.is_(True))
    )
    if setor_ids is not None:
        ids = list(setor_ids)
        if not ids:
            return []
        stmt = stmt.where(SaldoEstoque.setor_id.in_(ids))

    alertas: list[dict] = []
    for saldo, produto, setor in db.session.execute(stmt).all():
        disponivel = saldo.disponivel
        minimo = Decimal(str(produto.estoque_minimo or 0))
        zerado = disponivel <= 0
        abaixo_minimo = minimo > 0 and disponivel <= minimo
        if zerado or abaixo_minimo:
            alertas.append(
                {
                    "produto": produto,
                    "setor": setor,
                    "disponivel": disponivel,
                    "minimo": minimo,
                    "zerado": zerado,
                }
            )
    alertas.sort(key=lambda a: (not a["zerado"], a["produto"].nome))
    return alertas


def contar_alertas(organizacao_id: int, *, setor_ids: Iterable[int] | None = None) -> int:
    return len(itens_em_alerta(organizacao_id, setor_ids=setor_ids))
