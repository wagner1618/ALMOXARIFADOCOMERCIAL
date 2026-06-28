"""Serviço de empréstimos (§7.5) — consumível (por quantidade) ou durável (ativo).

Regras de ouro:
- Consumível: emprestar subtrai saldo do setor; devolver (total/parcial) repõe.
- Durável: emprestar leva o ativo a EMPRESTADO; devolução é integral e o ativo
  retorna a EM_ESTOQUE.
- Toda operação gera ``Movimentacao`` (EMPRESTIMO / DEVOLUCAO) append-only.
- Saldo nunca fica negativo; tudo é validado antes de gravar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models.ativo import BAIXADO, EM_ESTOQUE, EM_USO, EMPRESTADO, Ativo
from app.models.emprestimo import ATIVO, DEVOLVIDO, PARCIAL, Emprestimo
from app.models.movimentacao import DEVOLUCAO, EMPRESTIMO, Movimentacao
from app.services import estoque_service


class ErroEmprestimo(Exception):
    """Erro de regra de negócio em empréstimos."""


def _dec(valor: Any) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _validar_ativo(organizacao_id: int, ativo_id: int) -> Ativo:
    ativo = db.session.get(Ativo, ativo_id)
    if ativo is None or ativo.organizacao_id != organizacao_id:
        raise ErroEmprestimo("Ativo inválido para esta organização.")
    return ativo


def emprestar(
    organizacao_id: int,
    *,
    produto_id: int | None = None,
    ativo_id: int | None = None,
    setor_id: int | None = None,
    quantidade: Any = 1,
    destinatario: str | None = None,
    responsavel_id: int | None = None,
    data_prevista: date | None = None,
    data_emprestimo: date | None = None,
    observacoes: str | None = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Emprestimo:
    if bool(produto_id) == bool(ativo_id):
        raise ErroEmprestimo("Informe um produto consumível OU um ativo durável (não ambos).")
    if not (destinatario or "").strip() and responsavel_id is None:
        raise ErroEmprestimo("Informe o destinatário ou o responsável pelo empréstimo.")

    data_emprestimo = data_emprestimo or date.today()

    if ativo_id:
        ativo = _validar_ativo(organizacao_id, ativo_id)
        if ativo.status_ciclo == EMPRESTADO:
            raise ErroEmprestimo("Este ativo já está emprestado.")
        if ativo.status_ciclo not in (EM_ESTOQUE, EM_USO):
            raise ErroEmprestimo(
                f"Ativo indisponível para empréstimo (situação: {ativo.rotulo_status})."
            )
        origem_id = setor_id or ativo.setor_atual_id
        ativo.status_ciclo = EMPRESTADO
        quantidade = Decimal(1)
        _mov(
            organizacao_id, EMPRESTIMO, ativo_id=ativo.id, quantidade=Decimal(1),
            origem_setor_id=origem_id, destinatario=destinatario, usuario_id=usuario_id,
        )
    else:
        if setor_id is None:
            raise ErroEmprestimo("Informe o setor de origem do material.")
        quantidade = _dec(quantidade)
        if quantidade <= 0:
            raise ErroEmprestimo("A quantidade deve ser maior que zero.")
        produto = _produto_consumivel(organizacao_id, produto_id)
        saldo = estoque_service.obter_saldo(produto.id, setor_id)
        disponivel = saldo.disponivel if saldo else Decimal(0)
        if quantidade > disponivel:
            raise ErroEmprestimo(
                f"Saldo insuficiente: disponível {disponivel}, solicitado {quantidade}."
            )
        saldo.quantidade = _dec(saldo.quantidade) - quantidade
        _mov(
            organizacao_id, EMPRESTIMO, produto_id=produto.id, quantidade=quantidade,
            origem_setor_id=setor_id, destinatario=destinatario, usuario_id=usuario_id,
        )

    emprestimo = Emprestimo(
        organizacao_id=organizacao_id,
        produto_id=produto_id,
        ativo_id=ativo_id,
        quantidade=quantidade,
        quantidade_devolvida=Decimal(0),
        setor_id=setor_id,
        destinatario=(destinatario or "").strip() or None,
        responsavel_id=responsavel_id,
        data_emprestimo=data_emprestimo,
        data_prevista=data_prevista,
        status=ATIVO,
        observacoes=observacoes,
    )
    db.session.add(emprestimo)
    if commit:
        db.session.commit()
    return emprestimo


def devolver(
    emprestimo: Emprestimo,
    *,
    quantidade: Any = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> Emprestimo:
    if emprestimo.status == DEVOLVIDO:
        raise ErroEmprestimo("Empréstimo já devolvido.")

    if emprestimo.is_duravel:
        ativo = _validar_ativo(emprestimo.organizacao_id, emprestimo.ativo_id)
        if ativo.status_ciclo != BAIXADO:
            ativo.status_ciclo = EM_ESTOQUE
        emprestimo.quantidade_devolvida = emprestimo.quantidade
        _mov(
            emprestimo.organizacao_id, DEVOLUCAO, ativo_id=ativo.id, quantidade=Decimal(1),
            destino_setor_id=emprestimo.setor_id, usuario_id=usuario_id,
        )
    else:
        pendente = emprestimo.quantidade_pendente
        qtd = _dec(quantidade) if quantidade not in (None, "") else pendente
        if qtd <= 0:
            raise ErroEmprestimo("A quantidade devolvida deve ser maior que zero.")
        if qtd > pendente:
            raise ErroEmprestimo(
                f"Devolução excede o pendente (pendente {pendente}, informado {qtd})."
            )
        saldo = estoque_service.obter_ou_criar_saldo(
            emprestimo.organizacao_id, emprestimo.produto_id, emprestimo.setor_id
        )
        saldo.quantidade = _dec(saldo.quantidade) + qtd
        emprestimo.quantidade_devolvida = _dec(emprestimo.quantidade_devolvida) + qtd
        _mov(
            emprestimo.organizacao_id, DEVOLUCAO, produto_id=emprestimo.produto_id, quantidade=qtd,
            destino_setor_id=emprestimo.setor_id, usuario_id=usuario_id,
        )

    if emprestimo.quantidade_pendente <= 0:
        emprestimo.status = DEVOLVIDO
        emprestimo.data_devolucao = date.today()
    else:
        emprestimo.status = PARCIAL
    if commit:
        db.session.commit()
    return emprestimo


# ----------------------------------------------------------------- Helpers --- #
def _produto_consumivel(organizacao_id: int, produto_id: int):
    from app.models.produto import Produto

    produto = db.session.get(Produto, produto_id)
    if produto is None or produto.organizacao_id != organizacao_id:
        raise ErroEmprestimo("Produto inválido para esta organização.")
    if not produto.is_consumivel:
        raise ErroEmprestimo("Para itens duráveis empreste o ativo, não o produto.")
    return produto


def _mov(
    organizacao_id: int,
    tipo: str,
    *,
    produto_id: int | None = None,
    ativo_id: int | None = None,
    quantidade: Decimal,
    origem_setor_id: int | None = None,
    destino_setor_id: int | None = None,
    destinatario: str | None = None,
    usuario_id: int | None = None,
) -> None:
    db.session.add(
        Movimentacao(
            organizacao_id=organizacao_id,
            tipo=tipo,
            produto_id=produto_id,
            ativo_id=ativo_id,
            quantidade=quantidade,
            origem_setor_id=origem_setor_id,
            destino_setor_id=destino_setor_id,
            destinatario=destinatario,
            usuario_id=usuario_id,
        )
    )


def emprestimos_em_aberto(organizacao_id: int) -> list[Emprestimo]:
    """Empréstimos ainda pendentes (ATIVO/PARCIAL), para recibos e alertas."""
    from app.models.emprestimo import EM_ABERTO

    return list(
        db.session.scalars(
            select(Emprestimo)
            .where(
                Emprestimo.organizacao_id == organizacao_id,
                Emprestimo.status.in_(EM_ABERTO),
            )
            .order_by(Emprestimo.setor_id, Emprestimo.data_prevista)
        )
    )
