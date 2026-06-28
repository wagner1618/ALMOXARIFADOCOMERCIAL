"""Serviço de compras (§7.9): fornecedores, pedidos e notas fiscais.

Regras de ouro:
- Só setores com ``poder_compra`` registram pedidos e notas fiscais.
- O pedido segue o fluxo RASCUNHO → APROVADO → EMPENHADO → CONCLUÍDO (ou CANCELADO);
  só editável em rascunho.
- A aprovação controla o gasto contra o **orçamento anual** do setor (alerta sempre;
  bloqueio se ``config['bloquear_estouro_orcamento']``).
- A entrada física é **valorada a partir da NF**: consumível atualiza ``custo_medio``;
  durável gera ``Ativo`` com ``valor_aquisicao``. A NF lançada é imutável (idempotente).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.extensions import db
from app.models.compras import (
    APROVADO,
    CANCELADO,
    CONCLUIDO,
    EMPENHADO,
    NF_LANCADA,
    NF_REGISTRADA,
    RASCUNHO,
    STATUS_COMPROMETE_ORCAMENTO,
    NotaFiscal,
    NotaFiscalItem,
    PedidoCompra,
    PedidoCompraItem,
)
from app.models.fornecedor import Fornecedor
from app.models.organizacao import Organizacao
from app.models.produto import Produto
from app.models.setor import Setor
from app.services import ativo_service, estoque_service


class ErroCompra(Exception):
    """Erro de regra de negócio em compras."""


def _dec(valor: Any) -> Decimal:
    if valor in (None, ""):
        return Decimal(0)
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _validar_setor_compra(organizacao_id: int, setor_id: int) -> Setor:
    setor = db.session.get(Setor, setor_id)
    if setor is None or setor.organizacao_id != organizacao_id:
        raise ErroCompra("Setor inválido para esta organização.")
    if not setor.poder_compra:
        raise ErroCompra(f"O setor {setor.nome!r} não tem poder de compra.")
    return setor


def _validar_fornecedor(organizacao_id: int, fornecedor_id: int | None) -> Fornecedor | None:
    if fornecedor_id is None:
        return None
    fornecedor = db.session.get(Fornecedor, fornecedor_id)
    if fornecedor is None or fornecedor.organizacao_id != organizacao_id:
        raise ErroCompra("Fornecedor inválido para esta organização.")
    return fornecedor


# --------------------------------------------------------------- Orçamento --- #
def orcamento_consumido(
    setor_id: int, exercicio: int, *, ignorar_pedido_id: int | None = None
) -> Decimal:
    """Soma o valor estimado dos pedidos do setor que comprometem o orçamento."""
    stmt = select(func.coalesce(func.sum(PedidoCompra.valor_estimado), 0)).where(
        PedidoCompra.setor_id == setor_id,
        PedidoCompra.exercicio == exercicio,
        PedidoCompra.status.in_(STATUS_COMPROMETE_ORCAMENTO),
    )
    if ignorar_pedido_id is not None:
        stmt = stmt.where(PedidoCompra.id != ignorar_pedido_id)
    return _dec(db.session.scalar(stmt))


def checar_orcamento(setor: Setor, exercicio: int, valor_adicional: Any) -> dict[str, Any]:
    """Retorna a situação orçamentária do setor caso ``valor_adicional`` seja comprometido."""
    orcamento = _dec(setor.orcamento_anual) if setor.orcamento_anual is not None else None
    consumido = orcamento_consumido(setor.id, exercicio)
    projetado = consumido + _dec(valor_adicional)
    excede = orcamento is not None and projetado > orcamento
    return {
        "tem_orcamento": orcamento is not None,
        "orcamento": orcamento,
        "consumido": consumido,
        "projetado": projetado,
        "disponivel": (orcamento - consumido) if orcamento is not None else None,
        "excede": excede,
    }


# ------------------------------------------------------------- Fornecedor --- #
def criar_fornecedor(
    organizacao_id: int, *, dados: dict[str, Any], commit: bool = True
) -> Fornecedor:
    documento = (dados.get("documento") or "").strip() or None
    if documento and db.session.scalar(
        select(Fornecedor).where(
            Fornecedor.organizacao_id == organizacao_id, Fornecedor.documento == documento
        )
    ):
        raise ErroCompra("Já existe um fornecedor com este documento.")
    dados = {**dados, "documento": documento}
    fornecedor = Fornecedor(organizacao_id=organizacao_id, **dados)
    db.session.add(fornecedor)
    if commit:
        db.session.commit()
    return fornecedor


def atualizar_fornecedor(
    fornecedor: Fornecedor, *, dados: dict[str, Any], commit: bool = True
) -> Fornecedor:
    documento = (dados.get("documento") or "").strip() or None
    if documento and db.session.scalar(
        select(Fornecedor).where(
            Fornecedor.organizacao_id == fornecedor.organizacao_id,
            Fornecedor.documento == documento,
            Fornecedor.id != fornecedor.id,
        )
    ):
        raise ErroCompra("Já existe um fornecedor com este documento.")
    for campo, valor in {**dados, "documento": documento}.items():
        setattr(fornecedor, campo, valor)
    if commit:
        db.session.commit()
    return fornecedor


# ----------------------------------------------------------------- Pedido --- #
def proximo_numero_pedido(organizacao_id: int) -> int:
    maximo = db.session.scalar(
        select(func.coalesce(func.max(PedidoCompra.numero), 0)).where(
            PedidoCompra.organizacao_id == organizacao_id
        )
    )
    return int(maximo or 0) + 1


def _itens_para_modelo(itens: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal]:
    """Normaliza linhas de item e devolve (linhas_limpas, total)."""
    limpos: list[dict[str, Any]] = []
    total = Decimal(0)
    for item in itens:
        descricao = (item.get("descricao") or "").strip()
        produto_id = item.get("produto_id") or None
        if not descricao and not produto_id:
            continue
        quantidade = _dec(item.get("quantidade"))
        if quantidade <= 0:
            raise ErroCompra(f"Quantidade inválida para o item {descricao or produto_id!r}.")
        valor_unitario = _dec(item.get("valor_unitario"))
        valor_total = (quantidade * valor_unitario).quantize(Decimal("0.01"))
        limpos.append(
            {
                "produto_id": produto_id,
                "descricao": descricao or "(produto)",
                "quantidade": quantidade,
                "valor_unitario": valor_unitario,
                "valor_total": valor_total,
            }
        )
        total += valor_total
    if not limpos:
        raise ErroCompra("Informe ao menos um item.")
    return limpos, total


def criar_pedido(
    organizacao_id: int,
    *,
    setor_id: int,
    fornecedor_id: int | None,
    itens: list[dict[str, Any]],
    justificativa: str | None = None,
    observacoes: str | None = None,
    solicitante_id: int | None = None,
    exercicio: int | None = None,
    commit: bool = True,
) -> PedidoCompra:
    _validar_setor_compra(organizacao_id, setor_id)
    _validar_fornecedor(organizacao_id, fornecedor_id)
    linhas, total = _itens_para_modelo(itens)

    pedido = PedidoCompra(
        organizacao_id=organizacao_id,
        numero=proximo_numero_pedido(organizacao_id),
        exercicio=exercicio or date.today().year,
        setor_id=setor_id,
        fornecedor_id=fornecedor_id,
        status=RASCUNHO,
        valor_estimado=total,
        justificativa=justificativa,
        observacoes=observacoes,
        solicitante_id=solicitante_id,
    )
    pedido.itens = [PedidoCompraItem(organizacao_id=organizacao_id, **linha) for linha in linhas]
    db.session.add(pedido)
    if commit:
        db.session.commit()
    return pedido


def atualizar_pedido(
    pedido: PedidoCompra,
    *,
    fornecedor_id: int | None,
    itens: list[dict[str, Any]],
    justificativa: str | None = None,
    observacoes: str | None = None,
    commit: bool = True,
) -> PedidoCompra:
    if not pedido.editavel:
        raise ErroCompra("Só pedidos em rascunho podem ser editados.")
    _validar_fornecedor(pedido.organizacao_id, fornecedor_id)
    linhas, total = _itens_para_modelo(itens)

    pedido.fornecedor_id = fornecedor_id
    pedido.justificativa = justificativa
    pedido.observacoes = observacoes
    pedido.valor_estimado = total
    pedido.itens = [
        PedidoCompraItem(organizacao_id=pedido.organizacao_id, **linha) for linha in linhas
    ]
    if commit:
        db.session.commit()
    return pedido


def aprovar_pedido(
    pedido: PedidoCompra, *, aprovador_id: int | None = None, commit: bool = True
) -> PedidoCompra:
    if pedido.status != RASCUNHO:
        raise ErroCompra("Apenas pedidos em rascunho podem ser aprovados.")
    setor = _validar_setor_compra(pedido.organizacao_id, pedido.setor_id)

    org = db.session.get(Organizacao, pedido.organizacao_id)
    if (
        org is not None
        and org.config.get("aprovacao_dois_olhos")
        and aprovador_id is not None
        and pedido.solicitante_id == aprovador_id
    ):
        raise ErroCompra("Aprovação exige um responsável diferente do solicitante.")

    situacao = checar_orcamento(setor, pedido.exercicio, pedido.valor_estimado)
    if situacao["excede"] and org is not None and org.config.get("bloquear_estouro_orcamento"):
        raise ErroCompra(
            "Pedido excede o orçamento anual do setor "
            f"(disponível R$ {situacao['disponivel']}, pedido R$ {pedido.valor_estimado})."
        )

    pedido.status = APROVADO
    pedido.aprovador_id = aprovador_id
    pedido.data_aprovacao = date.today()
    if commit:
        db.session.commit()
    return pedido


def empenhar_pedido(pedido: PedidoCompra, *, commit: bool = True) -> PedidoCompra:
    if pedido.status != APROVADO:
        raise ErroCompra("Só pedidos aprovados podem ser empenhados.")
    pedido.status = EMPENHADO
    if commit:
        db.session.commit()
    return pedido


def concluir_pedido(pedido: PedidoCompra, *, commit: bool = True) -> PedidoCompra:
    if pedido.status not in (APROVADO, EMPENHADO):
        raise ErroCompra("Só pedidos aprovados/empenhados podem ser concluídos.")
    pedido.status = CONCLUIDO
    if commit:
        db.session.commit()
    return pedido


def cancelar_pedido(pedido: PedidoCompra, *, commit: bool = True) -> PedidoCompra:
    if pedido.status in (CONCLUIDO, CANCELADO):
        raise ErroCompra("Pedido já encerrado.")
    pedido.status = CANCELADO
    if commit:
        db.session.commit()
    return pedido


# ------------------------------------------------------------ Nota fiscal --- #
def registrar_nota(
    organizacao_id: int,
    *,
    fornecedor_id: int,
    setor_id: int,
    numero: str,
    serie: str | None = None,
    chave_nfe: str | None = None,
    pedido_id: int | None = None,
    data_emissao: date | None = None,
    data_entrada: date | None = None,
    itens: list[dict[str, Any]],
    arquivo_pdf: str | None = None,
    arquivo_xml: str | None = None,
    observacoes: str | None = None,
    usuario_id: int | None = None,
    commit: bool = True,
) -> NotaFiscal:
    _validar_setor_compra(organizacao_id, setor_id)
    if _validar_fornecedor(organizacao_id, fornecedor_id) is None:
        raise ErroCompra("A nota fiscal exige um fornecedor.")
    if not (numero or "").strip():
        raise ErroCompra("Informe o número da nota fiscal.")
    linhas, total = _itens_para_modelo(itens)

    nota = NotaFiscal(
        organizacao_id=organizacao_id,
        numero=numero.strip(),
        serie=(serie or "").strip() or None,
        chave_nfe=(chave_nfe or "").strip() or None,
        fornecedor_id=fornecedor_id,
        setor_id=setor_id,
        pedido_id=pedido_id,
        data_emissao=data_emissao,
        data_entrada=data_entrada or date.today(),
        valor_total=total,
        arquivo_pdf=arquivo_pdf,
        arquivo_xml=arquivo_xml,
        observacoes=observacoes,
        usuario_id=usuario_id,
        status=NF_REGISTRADA,
    )
    nota.itens = [NotaFiscalItem(organizacao_id=organizacao_id, **linha) for linha in linhas]
    db.session.add(nota)
    if commit:
        db.session.commit()
    return nota


def lancar_entrada_valorada(
    nota: NotaFiscal, *, usuario_id: int | None = None, commit: bool = True
) -> NotaFiscal:
    """Gera a entrada física valorada de cada item da NF. Idempotente: recusa se já lançada."""
    if nota.status == NF_LANCADA:
        raise ErroCompra("Esta nota fiscal já foi lançada.")

    org_id = nota.organizacao_id
    for item in nota.itens:
        if item.produto_id is None:
            raise ErroCompra(
                f"O item {item.descricao!r} não está vinculado a um produto do catálogo."
            )
        produto = db.session.get(Produto, item.produto_id)
        if produto is None or produto.organizacao_id != org_id:
            raise ErroCompra(f"Produto inválido no item {item.descricao!r}.")

        if produto.is_consumivel:
            estoque_service.entrada(
                org_id,
                produto_id=produto.id,
                setor_id=nota.setor_id,
                quantidade=item.quantidade,
                valor_unitario=item.valor_unitario,
                usuario_id=usuario_id,
                observacoes=f"Entrada da NF {nota.numero}",
                nota_fiscal_id=nota.id,
                commit=False,
            )
        else:
            unidades = int(item.quantidade)
            if unidades <= 0 or Decimal(unidades) != item.quantidade:
                raise ErroCompra(
                    f"Item durável {item.descricao!r} exige quantidade inteira (uma por exemplar)."
                )
            for _ in range(unidades):
                ativo_service.criar_ativo(
                    org_id,
                    dados={
                        "produto_id": produto.id,
                        "nome": produto.nome,
                        "marca": produto.marca,
                        "modelo": produto.modelo,
                        "fornecedor": nota.fornecedor.nome,
                        "data_aquisicao": nota.data_entrada,
                        "valor_aquisicao": item.valor_unitario,
                        "setor_atual_id": nota.setor_id,
                    },
                    usuario_id=usuario_id,
                    nota_fiscal_id=nota.id,
                    commit=False,
                )

    nota.status = NF_LANCADA
    if commit:
        db.session.commit()
    return nota
