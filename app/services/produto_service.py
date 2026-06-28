"""Serviço de produtos: SKU automático, criação e atualização."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models.produto import TIPO_CONSUMIVEL, TIPOS_CONTROLE, Produto


class ErroProduto(Exception):
    """Erro de regra de negócio em produtos."""


def gerar_sku(produto_id: int) -> str:
    return f"PRD-{produto_id:06d}"


def _sku_disponivel(organizacao_id: int, sku: str, ignorar_id: int | None = None) -> bool:
    stmt = select(Produto).where(Produto.organizacao_id == organizacao_id, Produto.sku == sku)
    if ignorar_id is not None:
        stmt = stmt.where(Produto.id != ignorar_id)
    return db.session.scalar(stmt) is None


def criar_produto(
    organizacao_id: int,
    *,
    nome: str,
    tipo_controle: str = TIPO_CONSUMIVEL,
    sku: str | None = None,
    categoria_id: int | None = None,
    unidade: str = "UN",
    estoque_minimo: float = 0,
    estoque_maximo: float | None = None,
    marca: str | None = None,
    modelo: str | None = None,
    valor_unitario_referencia: float | None = None,
    descricao: str | None = None,
    foto: str | None = None,
    campos: dict[str, Any] | None = None,
    commit: bool = True,
) -> Produto:
    if tipo_controle not in TIPOS_CONTROLE:
        raise ErroProduto("Tipo de controle inválido.")

    sku = (sku or "").strip() or None
    if sku and not _sku_disponivel(organizacao_id, sku):
        raise ErroProduto(f"O SKU “{sku}” já está em uso.")

    produto = Produto(
        organizacao_id=organizacao_id,
        nome=nome.strip(),
        sku=sku or "PENDENTE",
        tipo_controle=tipo_controle,
        categoria_id=categoria_id,
        unidade=unidade,
        estoque_minimo=estoque_minimo or 0,
        estoque_maximo=estoque_maximo,
        marca=marca or None,
        modelo=modelo or None,
        valor_unitario_referencia=valor_unitario_referencia,
        descricao=descricao or None,
        foto=foto,
        campos=campos or {},
    )
    db.session.add(produto)
    db.session.flush()
    if not sku:
        produto.sku = gerar_sku(produto.id)
    if commit:
        db.session.commit()
    return produto


def atualizar_produto(produto: Produto, *, dados: dict, commit: bool = True) -> Produto:
    novo_sku = (dados.get("sku") or "").strip()
    if novo_sku and novo_sku != produto.sku:
        if not _sku_disponivel(produto.organizacao_id, novo_sku, ignorar_id=produto.id):
            raise ErroProduto(f"O SKU “{novo_sku}” já está em uso.")
        produto.sku = novo_sku

    for campo in (
        "nome",
        "tipo_controle",
        "categoria_id",
        "unidade",
        "estoque_minimo",
        "estoque_maximo",
        "marca",
        "modelo",
        "valor_unitario_referencia",
        "descricao",
        "ativo",
    ):
        if campo in dados:
            setattr(produto, campo, dados[campo])

    if "campos" in dados:
        produto.campos = dados["campos"]
    if dados.get("foto"):
        produto.foto = dados["foto"]

    if commit:
        db.session.commit()
    return produto
