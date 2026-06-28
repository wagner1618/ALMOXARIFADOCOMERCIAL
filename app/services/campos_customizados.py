"""Motor de campos customizados: consulta, validação e formatação (§6).

Os valores são guardados na coluna ``campos`` (JSONB) da entidade, com a chave
da definição. A validação é **dirigida pela definição** e ocorre no servidor.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import or_, select
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models.definicao_campo import (
    TIPO_ARQUIVO,
    TIPO_BOOLEANO,
    TIPO_DATA,
    TIPO_MULTISELECT,
    TIPO_NUMERO,
    TIPO_SELECT,
    DefinicaoCampo,
)
from app.utils.formatacao import formatar_data, formatar_numero
from app.utils.uploads import ErroUpload, salvar_arquivo

# Prefixo dos nomes dos campos customizados no formulário (evita colisão).
PREFIXO = "cc_"


def nome_campo(definicao: DefinicaoCampo) -> str:
    return f"{PREFIXO}{definicao.chave}"


def definicoes_aplicaveis(
    organizacao_id: int,
    entidade: str,
    *,
    categoria_id: int | None = None,
    apenas_ativos: bool = True,
) -> list[DefinicaoCampo]:
    """Definições da entidade: globais + as da categoria informada."""
    stmt = select(DefinicaoCampo).where(
        DefinicaoCampo.organizacao_id == organizacao_id,
        DefinicaoCampo.entidade == entidade,
    )
    if apenas_ativos:
        stmt = stmt.where(DefinicaoCampo.ativo.is_(True))
    if categoria_id is None:
        stmt = stmt.where(DefinicaoCampo.aplica_a_categoria_id.is_(None))
    else:
        stmt = stmt.where(
            or_(
                DefinicaoCampo.aplica_a_categoria_id.is_(None),
                DefinicaoCampo.aplica_a_categoria_id == categoria_id,
            )
        )
    stmt = stmt.order_by(DefinicaoCampo.ordem, DefinicaoCampo.rotulo)
    return list(db.session.scalars(stmt))


def _parse_numero(bruto: str) -> float:
    return float(bruto.replace(".", "").replace(",", ".") if "," in bruto else bruto)


def _parse_data(bruto: str) -> str:
    bruto = bruto.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(bruto, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError


def validar_e_coletar(
    definicoes: list[DefinicaoCampo],
    form: Any,
    *,
    files: Any = None,
    valores_atuais: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    """Valida e coleta os valores customizados do formulário.

    Retorna ``(valores, erros)`` — ``erros`` é ``{chave: mensagem}``.
    """
    valores: dict[str, Any] = dict(valores_atuais or {})
    erros: dict[str, str] = {}

    for d in definicoes:
        campo = nome_campo(d)

        if d.tipo == TIPO_BOOLEANO:
            valores[d.chave] = bool(form.get(campo))
            continue

        if d.tipo == TIPO_MULTISELECT:
            selecionados = form.getlist(campo) if hasattr(form, "getlist") else form.get(campo, [])
            invalidos = [s for s in selecionados if s not in d.opcoes]
            if invalidos:
                erros[d.chave] = f"Opção inválida: {', '.join(invalidos)}"
            elif d.obrigatorio and not selecionados:
                erros[d.chave] = "Selecione ao menos uma opção."
            else:
                valores[d.chave] = selecionados
            continue

        if d.tipo == TIPO_ARQUIVO:
            arquivo: FileStorage | None = files.get(campo) if files else None
            if arquivo and arquivo.filename:
                try:
                    valores[d.chave] = salvar_arquivo(arquivo, subdir="campos")
                except ErroUpload as exc:
                    erros[d.chave] = str(exc)
            elif d.obrigatorio and not valores.get(d.chave):
                erros[d.chave] = "Anexo obrigatório."
            continue

        bruto = (form.get(campo) or "").strip()
        if not bruto:
            if d.obrigatorio:
                erros[d.chave] = "Campo obrigatório."
            else:
                valores.pop(d.chave, None)
            continue

        if d.tipo == TIPO_NUMERO:
            try:
                valores[d.chave] = _parse_numero(bruto)
            except ValueError:
                erros[d.chave] = "Informe um número válido."
        elif d.tipo == TIPO_DATA:
            try:
                valores[d.chave] = _parse_data(bruto)
            except ValueError:
                erros[d.chave] = "Data inválida (use dd/mm/aaaa)."
        elif d.tipo == TIPO_SELECT:
            if bruto not in d.opcoes:
                erros[d.chave] = "Opção inválida."
            else:
                valores[d.chave] = bruto
        else:  # TEXTO
            valores[d.chave] = bruto

    return valores, erros


def formatar_valor(definicao: DefinicaoCampo, valor: Any) -> str:
    """Representação amigável de um valor customizado (para listas/detalhe)."""
    if valor is None or valor == "" or valor == []:
        return "—"
    if definicao.tipo == TIPO_BOOLEANO:
        return "Sim" if valor else "Não"
    if definicao.tipo == TIPO_MULTISELECT:
        return ", ".join(valor) if isinstance(valor, list) else str(valor)
    if definicao.tipo == TIPO_NUMERO:
        return formatar_numero(valor)
    if definicao.tipo == TIPO_DATA:
        try:
            return formatar_data(date.fromisoformat(valor))
        except (ValueError, TypeError):
            return str(valor)
    return str(valor)


def valor_para_input(definicao: DefinicaoCampo, valor: Any) -> str:
    """Valor pré-preenchido para o input (data em dd/mm/aaaa)."""
    if valor is None:
        return ""
    if definicao.tipo == TIPO_DATA:
        try:
            return date.fromisoformat(valor).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return str(valor)
    if definicao.tipo == TIPO_NUMERO:
        return str(valor).replace(".", ",")
    return str(valor)
