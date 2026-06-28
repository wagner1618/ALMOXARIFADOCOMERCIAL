"""Serviço de ciclo de vida do ativo (durável/patrimônio).

Transições gravam ``Movimentacao`` (append-only). Inservível não pode ser
destinado/transferido para uso; baixa só para item justificado, em estoque e
não emprestado.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models.ativo import (
    BAIXADO,
    EM_ESTOQUE,
    EM_MANUTENCAO,
    EM_USO,
    EMPRESTADO,
    ESTADOS_CONSERVACAO,
    INSERVIVEL,
    Ativo,
)
from app.models.movimentacao import (
    AJUSTE_INVENTARIO,
    BAIXA,
    DEVOLUCAO,
    ENTRADA,
    TRANSFERENCIA,
    Movimentacao,
)


class ErroAtivo(Exception):
    """Erro de regra de negócio em ativos."""


def _mov(
    ativo: Ativo,
    tipo: str,
    *,
    origem_id: int | None = None,
    destino_id: int | None = None,
    usuario_id: int | None = None,
    obs: str | None = None,
) -> None:
    db.session.add(
        Movimentacao(
            organizacao_id=ativo.organizacao_id,
            tipo=tipo,
            ativo_id=ativo.id,
            quantidade=1,
            origem_setor_id=origem_id,
            destino_setor_id=destino_id,
            usuario_id=usuario_id,
            observacoes=obs,
        )
    )


def _validar_unicidade(
    organizacao_id: int,
    *,
    tombamento: str | None,
    numero_serie: str | None,
    ignorar_id: int | None = None,
) -> None:
    for campo, valor in (("tombamento", tombamento), ("numero_serie", numero_serie)):
        if not valor:
            continue
        stmt = select(Ativo).where(
            Ativo.organizacao_id == organizacao_id, getattr(Ativo, campo) == valor
        )
        if ignorar_id is not None:
            stmt = stmt.where(Ativo.id != ignorar_id)
        existente = db.session.scalar(stmt)
        if existente:
            rotulo = "tombamento" if campo == "tombamento" else "número de série"
            raise ErroAtivo(
                f"O {rotulo} “{valor}” já é usado pelo ativo "
                f"{existente.tombamento or existente.nome} (#{existente.id})."
            )


def criar_ativo(
    organizacao_id: int,
    *,
    dados: dict[str, Any],
    campos: dict | None = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Ativo:
    _validar_unicidade(
        organizacao_id,
        tombamento=dados.get("tombamento"),
        numero_serie=dados.get("numero_serie"),
    )
    ativo = Ativo(organizacao_id=organizacao_id, campos=campos or {}, **dados)
    if ativo.status_ciclo not in (EM_ESTOQUE,):
        ativo.status_ciclo = EM_ESTOQUE
    db.session.add(ativo)
    db.session.flush()
    _mov(
        ativo,
        ENTRADA,
        destino_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs="Cadastro do ativo no patrimônio",
    )
    if commit:
        db.session.commit()
    return ativo


def atualizar_ativo(
    ativo: Ativo, *, dados: dict[str, Any], campos: dict | None = None, commit: bool = True
) -> Ativo:
    _validar_unicidade(
        ativo.organizacao_id,
        tombamento=dados.get("tombamento", ativo.tombamento),
        numero_serie=dados.get("numero_serie", ativo.numero_serie),
        ignorar_id=ativo.id,
    )
    for campo, valor in dados.items():
        setattr(ativo, campo, valor)
    if campos is not None:
        ativo.campos = campos
    if commit:
        db.session.commit()
    return ativo


def _bloquear_se_baixado(ativo: Ativo) -> None:
    if ativo.status_ciclo == BAIXADO:
        raise ErroAtivo("Ativo baixado não pode ser movimentado.")


def destinar(
    ativo: Ativo,
    *,
    setor_id: int,
    responsavel_id: int | None = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Ativo:
    """Destina o ativo a um setor/usuário (EM_USO) — gera termo de responsabilidade."""
    _bloquear_se_baixado(ativo)
    if ativo.is_inservivel:
        raise ErroAtivo("Ativo inservível não pode ser destinado a uso.")
    if ativo.status_ciclo == EMPRESTADO:
        raise ErroAtivo("Ativo emprestado: registre a devolução antes.")

    origem = ativo.setor_atual_id
    ativo.setor_atual_id = setor_id
    ativo.usuario_responsavel_id = responsavel_id
    ativo.status_ciclo = EM_USO
    _mov(
        ativo,
        TRANSFERENCIA,
        origem_id=origem,
        destino_id=setor_id,
        usuario_id=usuario_id,
        obs="Destinação a uso (termo de responsabilidade)",
    )
    if commit:
        db.session.commit()
    return ativo


def transferir(
    ativo: Ativo, *, setor_id: int, usuario_id: int | None = None, commit: bool = True
) -> Ativo:
    """Transfere o ativo para outro setor, deixando-o EM_ESTOQUE no destino."""
    _bloquear_se_baixado(ativo)
    if ativo.is_inservivel:
        raise ErroAtivo("Ativo inservível não pode ser transferido para uso.")
    origem = ativo.setor_atual_id
    ativo.setor_atual_id = setor_id
    ativo.usuario_responsavel_id = None
    ativo.status_ciclo = EM_ESTOQUE
    _mov(
        ativo,
        TRANSFERENCIA,
        origem_id=origem,
        destino_id=setor_id,
        usuario_id=usuario_id,
        obs="Transferência/retorno do ativo",
    )
    if commit:
        db.session.commit()
    return ativo


def retornar_estoque(ativo: Ativo, *, usuario_id: int | None = None, commit: bool = True) -> Ativo:
    """Devolve o ativo ao estoque do setor atual (encerra o uso/responsável)."""
    _bloquear_se_baixado(ativo)
    ativo.usuario_responsavel_id = None
    ativo.status_ciclo = EM_ESTOQUE
    _mov(
        ativo,
        DEVOLUCAO,
        destino_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs="Retorno ao estoque",
    )
    if commit:
        db.session.commit()
    return ativo


def enviar_manutencao(ativo: Ativo, *, usuario_id: int | None = None, commit: bool = True) -> Ativo:
    _bloquear_se_baixado(ativo)
    ativo.status_ciclo = EM_MANUTENCAO
    _mov(
        ativo,
        AJUSTE_INVENTARIO,
        origem_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs="Enviado para manutenção",
    )
    if commit:
        db.session.commit()
    return ativo


def concluir_manutencao(
    ativo: Ativo,
    *,
    novo_estado: str | None = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Ativo:
    _bloquear_se_baixado(ativo)
    if novo_estado and novo_estado in ESTADOS_CONSERVACAO:
        ativo.estado_conservacao = novo_estado
    ativo.status_ciclo = EM_ESTOQUE
    _mov(
        ativo,
        AJUSTE_INVENTARIO,
        destino_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs="Manutenção concluída",
    )
    if commit:
        db.session.commit()
    return ativo


def baixar(
    ativo: Ativo, *, justificativa: str, usuario_id: int | None = None, commit: bool = True
) -> Ativo:
    """Baixa definitiva: só em estoque/manutenção, não emprestado, com justificativa."""
    if not justificativa or not justificativa.strip():
        raise ErroAtivo("A baixa exige justificativa.")
    if ativo.status_ciclo == BAIXADO:
        raise ErroAtivo("Ativo já está baixado.")
    if ativo.status_ciclo in (EMPRESTADO, EM_USO):
        raise ErroAtivo("Recolha o ativo (retorno ao estoque) antes de dar baixa.")

    ativo.status_ciclo = BAIXADO
    ativo.ativo = False
    _mov(
        ativo,
        BAIXA,
        origem_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs=f"Baixa: {justificativa.strip()}",
    )
    if commit:
        db.session.commit()
    return ativo


def recertificar(
    ativo: Ativo,
    *,
    estado_conservacao: str,
    status_ciclo: str | None = None,
    meses_proxima: int = 12,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Ativo:
    """Recertificação (inventário anual): atualiza estado e agenda a próxima revisão."""
    if estado_conservacao not in ESTADOS_CONSERVACAO:
        raise ErroAtivo("Estado de conservação inválido.")
    ativo.estado_conservacao = estado_conservacao
    if status_ciclo:
        ativo.status_ciclo = status_ciclo
    ativo.ultima_revisao_em = date.today()
    ativo.proxima_revisao_em = date.today() + timedelta(days=30 * meses_proxima)
    if estado_conservacao == INSERVIVEL and ativo.status_ciclo == EM_USO:
        # Inservível some das ações de uso: volta ao estoque para tratamento.
        ativo.status_ciclo = EM_ESTOQUE
        ativo.usuario_responsavel_id = None
    _mov(
        ativo,
        AJUSTE_INVENTARIO,
        destino_id=ativo.setor_atual_id,
        usuario_id=usuario_id,
        obs=f"Recertificação: {estado_conservacao}",
    )
    if commit:
        db.session.commit()
    return ativo
