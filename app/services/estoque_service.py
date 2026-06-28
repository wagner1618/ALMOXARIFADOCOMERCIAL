"""Serviço de estoque (consumíveis): entrada, saída, ajuste e lote — atômico.

Regras de ouro:
- Saldo nunca é editado à mão — só por movimentação, dentro de transação.
- Saldo disponível nunca fica negativo.
- ``custo_medio`` do produto é atualizado (média ponderada) nas entradas com valor.
- Toda operação gera uma ``Movimentacao`` append-only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.estoque import SaldoEstoque
from app.models.movimentacao import (
    AJUSTE_INVENTARIO,
    ENTRADA,
    SAIDA,
    LoteMovimentacao,
    Movimentacao,
)
from app.models.produto import Produto


class ErroEstoque(Exception):
    """Erro de regra de negócio em operações de estoque."""


def _dec(valor: Any) -> Decimal:
    if valor is None:
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def obter_saldo(produto_id: int, setor_id: int) -> SaldoEstoque | None:
    return db.session.scalar(
        select(SaldoEstoque).where(
            SaldoEstoque.produto_id == produto_id, SaldoEstoque.setor_id == setor_id
        )
    )


def _saldo_ou_cria(organizacao_id: int, produto_id: int, setor_id: int) -> SaldoEstoque:
    saldo = obter_saldo(produto_id, setor_id)
    if saldo is None:
        saldo = SaldoEstoque(
            organizacao_id=organizacao_id,
            produto_id=produto_id,
            setor_id=setor_id,
            quantidade=Decimal(0),
            quantidade_em_transito=Decimal(0),
        )
        db.session.add(saldo)
        db.session.flush()
    return saldo


def _validar_produto(organizacao_id: int, produto_id: int) -> Produto:
    produto = db.session.get(Produto, produto_id)
    if produto is None or produto.organizacao_id != organizacao_id:
        raise ErroEstoque("Produto inválido para esta organização.")
    if not produto.is_consumivel:
        raise ErroEstoque("Controle de saldo só se aplica a produtos consumíveis.")
    return produto


def _quantidade_total_org(produto_id: int) -> Decimal:
    total = db.session.scalar(
        select(func.coalesce(func.sum(SaldoEstoque.quantidade), 0)).where(
            SaldoEstoque.produto_id == produto_id
        )
    )
    return _dec(total)


def _atualizar_custo_medio(produto: Produto, quantidade: Decimal, valor_unitario: Decimal) -> None:
    """Média ponderada com a quantidade total do produto na organização."""
    total_anterior = _quantidade_total_org(produto.id)
    custo_anterior = _dec(produto.custo_medio)
    novo_total = total_anterior + quantidade
    if novo_total <= 0:
        return
    produto.custo_medio = (
        total_anterior * custo_anterior + quantidade * valor_unitario
    ) / novo_total


def proximo_numero_lote(organizacao_id: int) -> int:
    maximo = db.session.scalar(
        select(func.coalesce(func.max(LoteMovimentacao.numero), 0)).where(
            LoteMovimentacao.organizacao_id == organizacao_id
        )
    )
    return int(maximo or 0) + 1


def entrada(
    organizacao_id: int,
    *,
    produto_id: int,
    setor_id: int,
    quantidade: Any,
    valor_unitario: Any = None,
    usuario_id: int | None = None,
    observacoes: str | None = None,
    lote_id: int | None = None,
    commit: bool = True,
) -> Movimentacao:
    quantidade = _dec(quantidade)
    if quantidade <= 0:
        raise ErroEstoque("A quantidade deve ser maior que zero.")

    produto = _validar_produto(organizacao_id, produto_id)
    valor = _dec(valor_unitario) if valor_unitario not in (None, "") else None

    if valor is not None:
        _atualizar_custo_medio(produto, quantidade, valor)

    saldo = _saldo_ou_cria(organizacao_id, produto_id, setor_id)
    saldo.quantidade = _dec(saldo.quantidade) + quantidade

    mov = Movimentacao(
        organizacao_id=organizacao_id,
        tipo=ENTRADA,
        produto_id=produto_id,
        quantidade=quantidade,
        destino_setor_id=setor_id,
        valor_unitario=valor,
        valor_total=(valor * quantidade) if valor is not None else None,
        usuario_id=usuario_id,
        observacoes=observacoes,
        lote_id=lote_id,
    )
    db.session.add(mov)
    if commit:
        db.session.commit()
    return mov


def saida(
    organizacao_id: int,
    *,
    produto_id: int,
    setor_id: int,
    quantidade: Any,
    usuario_id: int | None = None,
    destinatario: str | None = None,
    observacoes: str | None = None,
    lote_id: int | None = None,
    commit: bool = True,
) -> Movimentacao:
    quantidade = _dec(quantidade)
    if quantidade <= 0:
        raise ErroEstoque("A quantidade deve ser maior que zero.")

    _validar_produto(organizacao_id, produto_id)
    saldo = obter_saldo(produto_id, setor_id)
    disponivel = saldo.disponivel if saldo else Decimal(0)
    if quantidade > disponivel:
        raise ErroEstoque(f"Saldo insuficiente: disponível {disponivel}, solicitado {quantidade}.")

    saldo.quantidade = _dec(saldo.quantidade) - quantidade

    mov = Movimentacao(
        organizacao_id=organizacao_id,
        tipo=SAIDA,
        produto_id=produto_id,
        quantidade=quantidade,
        origem_setor_id=setor_id,
        usuario_id=usuario_id,
        destinatario=destinatario,
        observacoes=observacoes,
        lote_id=lote_id,
    )
    db.session.add(mov)
    if commit:
        db.session.commit()
    return mov


def ajustar(
    organizacao_id: int,
    *,
    produto_id: int,
    setor_id: int,
    nova_quantidade: Any,
    justificativa: str,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Movimentacao:
    """Ajuste de inventário: define o saldo e registra a diferença com justificativa."""
    if not justificativa or not justificativa.strip():
        raise ErroEstoque("Ajuste exige justificativa.")
    nova_quantidade = _dec(nova_quantidade)
    if nova_quantidade < 0:
        raise ErroEstoque("A quantidade não pode ser negativa.")

    _validar_produto(organizacao_id, produto_id)
    saldo = _saldo_ou_cria(organizacao_id, produto_id, setor_id)
    diferenca = nova_quantidade - _dec(saldo.quantidade)
    saldo.quantidade = nova_quantidade

    mov = Movimentacao(
        organizacao_id=organizacao_id,
        tipo=AJUSTE_INVENTARIO,
        produto_id=produto_id,
        quantidade=abs(diferenca),
        origem_setor_id=setor_id if diferenca < 0 else None,
        destino_setor_id=setor_id if diferenca >= 0 else None,
        usuario_id=usuario_id,
        observacoes=justificativa.strip(),
    )
    db.session.add(mov)
    if commit:
        db.session.commit()
    return mov


def processar_lote(
    organizacao_id: int,
    *,
    operacoes: list[dict[str, Any]],
    usuario_id: int | None = None,
    observacoes: str | None = None,
) -> LoteMovimentacao:
    """Aplica várias entradas/saídas atomicamente. Valida tudo antes de gravar.

    ``operacoes``: lista de ``{"tipo": "ENTRADA"|"SAIDA", "produto_id", "setor_id",
    "quantidade", "valor_unitario"?}``. Se qualquer uma falhar, nada é gravado e os
    erros (com índice) são levantados.
    """
    if not operacoes:
        raise ErroEstoque("Informe ao menos uma linha.")

    erros: list[str] = []
    lote = LoteMovimentacao(
        organizacao_id=organizacao_id,
        numero=proximo_numero_lote(organizacao_id),
        usuario_id=usuario_id,
        observacoes=observacoes,
    )
    db.session.add(lote)
    db.session.flush()

    for i, op in enumerate(operacoes, start=1):
        tipo = op.get("tipo")
        try:
            if tipo == ENTRADA:
                entrada(
                    organizacao_id,
                    produto_id=op["produto_id"],
                    setor_id=op["setor_id"],
                    quantidade=op["quantidade"],
                    valor_unitario=op.get("valor_unitario"),
                    usuario_id=usuario_id,
                    lote_id=lote.id,
                    commit=False,
                )
            elif tipo == SAIDA:
                saida(
                    organizacao_id,
                    produto_id=op["produto_id"],
                    setor_id=op["setor_id"],
                    quantidade=op["quantidade"],
                    usuario_id=usuario_id,
                    destinatario=op.get("destinatario"),
                    lote_id=lote.id,
                    commit=False,
                )
            else:
                raise ErroEstoque(f"Tipo inválido: {tipo}")
        except ErroEstoque as exc:
            erros.append(f"Linha {i}: {exc}")

    if erros:
        db.session.rollback()
        raise ErroEstoque(" | ".join(erros))

    db.session.commit()
    return lote
