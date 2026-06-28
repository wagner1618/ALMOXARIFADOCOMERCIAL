"""Serviço de inventário (§7.4/§8) — recontagem de consumíveis e recertificação de ativos.

Regras de ouro:
- Abrir tira um snapshot do esperado (saldo / estado-situação) — não altera nada.
- Fechar é a única etapa que muda dados: consumível gera ``AJUSTE_INVENTARIO`` por
  divergência; ativo confirma estado/situação e renova as datas de revisão.
- Tudo dentro de transação; inventário fechado/cancelado é imutável.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.ativo import BAIXADO, ESTADOS_CONSERVACAO, STATUS_CICLO, Ativo
from app.models.estoque import SaldoEstoque
from app.models.inventario import (
    ABERTO,
    CANCELADO,
    FECHADO,
    INV_CONSUMIVEL,
    TIPOS_INVENTARIO,
    Inventario,
    InventarioItem,
)
from app.services import estoque_service


class ErroInventario(Exception):
    """Erro de regra de negócio em inventário."""


def _dec(valor: Any) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def proximo_numero(organizacao_id: int) -> int:
    maximo = db.session.scalar(
        select(func.coalesce(func.max(Inventario.numero), 0)).where(
            Inventario.organizacao_id == organizacao_id
        )
    )
    return int(maximo or 0) + 1


def abrir_inventario(
    organizacao_id: int,
    *,
    tipo: str,
    setor_id: int,
    responsavel_id: int | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> Inventario:
    if tipo not in TIPOS_INVENTARIO:
        raise ErroInventario("Tipo de inventário inválido.")

    inventario = Inventario(
        organizacao_id=organizacao_id,
        numero=proximo_numero(organizacao_id),
        tipo=tipo,
        setor_id=setor_id,
        status=ABERTO,
        data_inicio=date.today(),
        responsavel_id=responsavel_id,
        observacoes=observacoes,
    )
    db.session.add(inventario)
    db.session.flush()

    if tipo == INV_CONSUMIVEL:
        saldos = db.session.scalars(
            select(SaldoEstoque).where(
                SaldoEstoque.organizacao_id == organizacao_id,
                SaldoEstoque.setor_id == setor_id,
            )
        )
        for saldo in saldos:
            db.session.add(
                InventarioItem(
                    organizacao_id=organizacao_id,
                    inventario_id=inventario.id,
                    produto_id=saldo.produto_id,
                    quantidade_esperada=_dec(saldo.quantidade),
                )
            )
    else:
        ativos = db.session.scalars(
            select(Ativo).where(
                Ativo.organizacao_id == organizacao_id,
                Ativo.setor_atual_id == setor_id,
                Ativo.status_ciclo != BAIXADO,
            )
        )
        for ativo in ativos:
            db.session.add(
                InventarioItem(
                    organizacao_id=organizacao_id,
                    inventario_id=inventario.id,
                    ativo_id=ativo.id,
                    estado_conservacao=ativo.estado_conservacao,
                    status_ciclo=ativo.status_ciclo,
                )
            )

    if commit:
        db.session.commit()
    return inventario


def registrar_contagem(
    item: InventarioItem,
    *,
    quantidade: Any = None,
    estado_conservacao: str | None = None,
    status_ciclo: str | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> InventarioItem:
    if not item.inventario.aberto:
        raise ErroInventario("Inventário não está em contagem.")

    if item.produto_id is not None:
        contada = _dec(quantidade)
        if contada < 0:
            raise ErroInventario("A quantidade contada não pode ser negativa.")
        item.quantidade_contada = contada
        item.divergencia = contada != _dec(item.quantidade_esperada)
    else:
        if estado_conservacao and estado_conservacao not in ESTADOS_CONSERVACAO:
            raise ErroInventario("Estado de conservação inválido.")
        if status_ciclo and status_ciclo not in STATUS_CICLO:
            raise ErroInventario("Situação inválida.")
        ativo = item.ativo
        novo_estado = estado_conservacao or item.estado_conservacao
        novo_status = status_ciclo or item.status_ciclo
        item.estado_conservacao = novo_estado
        item.status_ciclo = novo_status
        item.divergencia = ativo is not None and (
            novo_estado != ativo.estado_conservacao or novo_status != ativo.status_ciclo
        )

    item.contado = True
    if observacoes is not None:
        item.observacoes = observacoes
    if commit:
        db.session.commit()
    return item


def fechar_inventario(
    inventario: Inventario, *, usuario_id: int | None = None, commit: bool = True
) -> Inventario:
    if inventario.status != ABERTO:
        raise ErroInventario("Apenas inventários em contagem podem ser fechados.")

    if inventario.is_consumivel:
        for item in inventario.itens:
            if item.contado and item.divergencia and item.produto_id is not None:
                estoque_service.ajustar(
                    inventario.organizacao_id,
                    produto_id=item.produto_id,
                    setor_id=inventario.setor_id,
                    nova_quantidade=_dec(item.quantidade_contada),
                    justificativa=f"Inventário #{inventario.numero}",
                    usuario_id=usuario_id,
                    commit=False,
                )
    else:
        proxima = date.today() + timedelta(days=365)
        for item in inventario.itens:
            if item.contado and item.ativo is not None:
                if item.estado_conservacao:
                    item.ativo.estado_conservacao = item.estado_conservacao
                if item.status_ciclo:
                    item.ativo.status_ciclo = item.status_ciclo
                item.ativo.ultima_revisao_em = date.today()
                item.ativo.proxima_revisao_em = proxima

    inventario.status = FECHADO
    inventario.data_fechamento = date.today()
    if commit:
        db.session.commit()
    return inventario


def cancelar_inventario(inventario: Inventario, *, commit: bool = True) -> Inventario:
    if inventario.status != ABERTO:
        raise ErroInventario("Apenas inventários em contagem podem ser cancelados.")
    inventario.status = CANCELADO
    inventario.data_fechamento = date.today()
    if commit:
        db.session.commit()
    return inventario


def ativos_revisao_vencida(organizacao_id: int, *, setor_ids=None) -> list[Ativo]:
    """Ativos com ``proxima_revisao_em`` no passado (alerta de recertificação)."""
    stmt = select(Ativo).where(
        Ativo.organizacao_id == organizacao_id,
        Ativo.ativo.is_(True),
        Ativo.status_ciclo != BAIXADO,
        Ativo.proxima_revisao_em.is_not(None),
        Ativo.proxima_revisao_em < date.today(),
    )
    if setor_ids is not None:
        ids = list(setor_ids)
        if not ids:
            return []
        stmt = stmt.where(Ativo.setor_atual_id.in_(ids))
    return list(db.session.scalars(stmt.order_by(Ativo.proxima_revisao_em)))
