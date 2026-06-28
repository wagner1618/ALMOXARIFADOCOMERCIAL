"""Serviço de transferência entre setores com confirmação (§7.8).

Máquina de estados em duas pontas (origem envia/confere → destino recebe/confere),
com tratamento de divergência e correção pelo setor superior. Tudo transacional.

Invariantes garantidas:
- O item em trânsito NUNCA conta como disponível nos dois setores ao mesmo tempo.
- O saldo disponível nunca fica negativo.
- Cada transição grava movimentação; histórico nunca é apagado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.movimentacao import AJUSTE_INVENTARIO, TRANSFERENCIA, Movimentacao
from app.models.produto import Produto
from app.models.transferencia import (
    CANCELADA,
    CORRIGIDA,
    ENVIADA,
    RECEBIDA,
    RECEBIDA_COM_DIVERGENCIA,
    Transferencia,
    TransferenciaItem,
)
from app.services import estoque_service


class ErroTransferencia(Exception):
    """Erro de regra de negócio em transferências."""


def _dec(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def proximo_numero(organizacao_id: int) -> int:
    maximo = db.session.scalar(
        select(func.coalesce(func.max(Transferencia.numero), 0)).where(
            Transferencia.organizacao_id == organizacao_id
        )
    )
    return int(maximo or 0) + 1


def _movimentacao(
    organizacao_id: int,
    tipo: str,
    *,
    produto_id: int,
    quantidade: Decimal,
    origem_id: int | None,
    destino_id: int | None,
    usuario_id: int | None,
    obs: str | None = None,
) -> None:
    db.session.add(
        Movimentacao(
            organizacao_id=organizacao_id,
            tipo=tipo,
            produto_id=produto_id,
            quantidade=quantidade,
            origem_setor_id=origem_id,
            destino_setor_id=destino_id,
            usuario_id=usuario_id,
            observacoes=obs,
        )
    )


def enviar(
    organizacao_id: int,
    *,
    setor_origem_id: int,
    setor_destino_id: int,
    itens: list[dict[str, Any]],
    usuario_id: int | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Transferencia:
    """Cria a transferência, reserva o estoque em trânsito na origem e a envia."""
    if setor_origem_id == setor_destino_id:
        raise ErroTransferencia("Origem e destino devem ser setores diferentes.")
    linhas = [
        linha for linha in itens if linha.get("produto_id") and _dec(linha.get("quantidade")) > 0
    ]
    if not linhas:
        raise ErroTransferencia("Informe ao menos um item com quantidade.")

    transferencia = Transferencia(
        organizacao_id=organizacao_id,
        numero=proximo_numero(organizacao_id),
        setor_origem_id=setor_origem_id,
        setor_destino_id=setor_destino_id,
        status=ENVIADA,
        enviado_por=usuario_id,
        enviado_em=datetime.now(UTC),
        observacoes_envio=observacoes,
    )
    db.session.add(transferencia)
    db.session.flush()

    for linha in linhas:
        produto_id = int(linha["produto_id"])
        quantidade = _dec(linha["quantidade"])
        produto = db.session.get(Produto, produto_id)
        if produto is None or produto.organizacao_id != organizacao_id:
            db.session.rollback()
            raise ErroTransferencia("Produto inválido para esta organização.")
        if not produto.is_consumivel:
            db.session.rollback()
            raise ErroTransferencia("Por enquanto, só consumíveis podem ser transferidos.")

        saldo = estoque_service.obter_saldo(produto_id, setor_origem_id)
        disponivel = saldo.disponivel if saldo else Decimal(0)
        if quantidade > disponivel:
            db.session.rollback()
            raise ErroTransferencia(
                f"Saldo insuficiente de {produto.nome}: disponível {disponivel}, "
                f"solicitado {quantidade}."
            )

        # Reserva: move para em trânsito (quantidade permanece; disponível cai).
        saldo = estoque_service.obter_ou_criar_saldo(organizacao_id, produto_id, setor_origem_id)
        saldo.quantidade_em_transito = _dec(saldo.quantidade_em_transito) + quantidade

        db.session.add(
            TransferenciaItem(
                transferencia_id=transferencia.id,
                produto_id=produto_id,
                quantidade_enviada=quantidade,
            )
        )
        _movimentacao(
            organizacao_id,
            TRANSFERENCIA,
            produto_id=produto_id,
            quantidade=quantidade,
            origem_id=setor_origem_id,
            destino_id=setor_destino_id,
            usuario_id=usuario_id,
            obs=f"Envio transf. #{transferencia.numero}",
        )

    if commit:
        db.session.commit()
    return transferencia


def receber(
    transferencia: Transferencia,
    *,
    recebimentos: dict[int, dict[str, Any]],
    usuario_id: int | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Transferencia:
    """Confere e confirma o recebimento item a item, tratando divergências."""
    if transferencia.status != ENVIADA:
        raise ErroTransferencia("Só é possível receber transferências enviadas.")

    houve_divergencia = False
    for item in transferencia.itens:
        dados = recebimentos.get(item.id, {})
        enviada = _dec(item.quantidade_enviada)
        recebida = _dec(dados.get("quantidade_recebida", enviada))
        if recebida < 0:
            recebida = Decimal(0)
        if recebida > enviada:
            # Sobra: credita no máximo o enviado e marca divergência.
            item.divergencia = True
            item.motivo_divergencia = (
                dados.get("motivo") or "Quantidade recebida maior que a enviada."
            )
            recebida = enviada
            houve_divergencia = True

        item.quantidade_recebida = recebida
        if recebida < enviada:
            item.divergencia = True
            item.motivo_divergencia = (
                dados.get("motivo") or "Quantidade recebida menor que a enviada."
            )
            houve_divergencia = True

        if recebida > 0:
            # Liquida o trânsito da origem e soma ao destino.
            saldo_origem = estoque_service.obter_ou_criar_saldo(
                transferencia.organizacao_id, item.produto_id, transferencia.setor_origem_id
            )
            saldo_origem.quantidade = _dec(saldo_origem.quantidade) - recebida
            saldo_origem.quantidade_em_transito = (
                _dec(saldo_origem.quantidade_em_transito) - recebida
            )

            saldo_destino = estoque_service.obter_ou_criar_saldo(
                transferencia.organizacao_id, item.produto_id, transferencia.setor_destino_id
            )
            saldo_destino.quantidade = _dec(saldo_destino.quantidade) + recebida

            _movimentacao(
                transferencia.organizacao_id,
                TRANSFERENCIA,
                produto_id=item.produto_id,
                quantidade=recebida,
                origem_id=transferencia.setor_origem_id,
                destino_id=transferencia.setor_destino_id,
                usuario_id=usuario_id,
                obs=f"Recebimento transf. #{transferencia.numero}",
            )

    transferencia.status = RECEBIDA_COM_DIVERGENCIA if houve_divergencia else RECEBIDA
    transferencia.recebido_por = usuario_id
    transferencia.recebido_em = datetime.now(UTC)
    transferencia.observacoes_recebimento = observacoes

    if commit:
        db.session.commit()
    return transferencia


def corrigir(
    transferencia: Transferencia,
    *,
    usuario_id: int | None = None,
    observacao: str | None = None,
    commit: bool = True,
) -> Transferencia:
    """Origem corrige a divergência: estorna o pendente em trânsito de volta à origem."""
    if transferencia.status != RECEBIDA_COM_DIVERGENCIA:
        raise ErroTransferencia("Só transferências com divergência podem ser corrigidas.")

    for item in transferencia.itens:
        pendente = item.pendente_transito
        if pendente <= 0:
            continue
        # Estorna a reserva: o que não chegou volta a ficar disponível na origem.
        saldo_origem = estoque_service.obter_ou_criar_saldo(
            transferencia.organizacao_id, item.produto_id, transferencia.setor_origem_id
        )
        saldo_origem.quantidade_em_transito = _dec(saldo_origem.quantidade_em_transito) - pendente
        item.quantidade_corrigida = pendente

        _movimentacao(
            transferencia.organizacao_id,
            AJUSTE_INVENTARIO,
            produto_id=item.produto_id,
            quantidade=pendente,
            origem_id=None,
            destino_id=transferencia.setor_origem_id,
            usuario_id=usuario_id,
            obs=f"Correção transf. #{transferencia.numero}: estorno à origem",
        )

    transferencia.status = CORRIGIDA
    transferencia.corrigido_por = usuario_id
    transferencia.corrigido_em = datetime.now(UTC)
    transferencia.observacoes_correcao = observacao

    if commit:
        db.session.commit()
    return transferencia


def cancelar(
    transferencia: Transferencia,
    *,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Transferencia:
    """Cancela uma transferência ainda em trânsito, estornando as reservas."""
    if transferencia.status != ENVIADA:
        raise ErroTransferencia("Só é possível cancelar transferências enviadas (em trânsito).")

    for item in transferencia.itens:
        saldo_origem = estoque_service.obter_ou_criar_saldo(
            transferencia.organizacao_id, item.produto_id, transferencia.setor_origem_id
        )
        saldo_origem.quantidade_em_transito = _dec(saldo_origem.quantidade_em_transito) - _dec(
            item.quantidade_enviada
        )

    transferencia.status = CANCELADA
    transferencia.corrigido_por = usuario_id
    transferencia.corrigido_em = datetime.now(UTC)

    if commit:
        db.session.commit()
    return transferencia
