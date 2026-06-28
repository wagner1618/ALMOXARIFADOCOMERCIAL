"""Serviço de documentos (§7.7) — emissão numerada, com hash e snapshot.

- Numeração sequencial por organização/tipo/ano: ``SAIDA-2026-000123``.
- HTML renderizado a partir de um ``ModeloDocumento`` (Jinja **em sandbox**, para
  não permitir execução arbitrária no template editável pela organização).
- PDF via WeasyPrint **se instalado**; senão o documento é gravado como HTML
  imprimível (o subsistema funciona sem a dependência nativa).
- ``hash`` SHA-256 do arquivo e ``dados`` (snapshot JSONB) garantem integridade e
  reimpressão fiel.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import current_app
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import func, select

from app.extensions import db
from app.models.documento import (
    ROTULO_DOCUMENTO,
    TIPOS_DOCUMENTO,
    Documento,
    ModeloDocumento,
)
from app.models.movimentacao import Movimentacao
from app.models.organizacao import Organizacao

_SANDBOX = SandboxedEnvironment(autoescape=True)


class ErroDocumento(Exception):
    """Erro de regra de negócio na emissão de documentos."""


# Modelo padrão (usado quando a organização ainda não personalizou o tipo).
MODELO_PADRAO = """\
<html><head><meta charset="utf-8"><style>
  body { font-family: sans-serif; color: #222; font-size: 12px; }
  h1 { font-size: 18px; margin: 0; }
  .cab { border-bottom: 2px solid #444; padding-bottom: 8px; margin-bottom: 12px;
         display: flex; justify-content: space-between; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; }
  th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; }
  th { background: #f0f0f0; }
  .ass { display: flex; justify-content: space-between; margin-top: 48px; }
  .ass div { width: 45%; border-top: 1px solid #444; text-align: center; padding-top: 4px; }
</style></head><body>
  <div class="cab">
    <div><h1>{{ organizacao.nome }}</h1><small>{{ organizacao.cnpj or '' }}</small></div>
    <div style="text-align:right">
      <strong>{{ documento.rotulo_tipo }}</strong><br>
      Nº {{ documento.numero }}<br>{{ documento.data }}
    </div>
  </div>
  {% if origem or destino or destinatario %}
  <p>
    {% if origem %}<strong>Origem:</strong> {{ origem }}<br>{% endif %}
    {% if destino %}<strong>Destino:</strong> {{ destino }}<br>{% endif %}
    {% if destinatario %}<strong>Destinatário:</strong> {{ destinatario }}{% endif %}
  </p>
  {% endif %}
  {% if itens %}
  <table>
    <thead><tr><th>Item</th><th>Qtd.</th><th>Observação</th></tr></thead>
    <tbody>
      {% for it in itens %}
      <tr><td>{{ it.descricao }}</td><td>{{ it.quantidade }}</td>
          <td>{{ it.observacao or '' }}</td></tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% if observacoes %}<p><strong>Observações:</strong> {{ observacoes }}</p>{% endif %}
  <div class="ass">
    <div>Responsável pela emissão</div>
    <div>Responsável pelo recebimento</div>
  </div>
</body></html>
"""


def _dir() -> Path:
    base = Path(current_app.config["UPLOAD_DIR"]) / "documentos"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _jsonable(valor: Any) -> Any:
    """Converte Decimals/datas para tipos serializáveis no snapshot JSONB."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonable(v) for v in valor]
    return valor


def proximo_sequencial(organizacao_id: int, tipo: str, ano: int) -> int:
    maximo = db.session.scalar(
        select(func.coalesce(func.max(Documento.sequencial), 0)).where(
            Documento.organizacao_id == organizacao_id,
            Documento.tipo == tipo,
            Documento.ano == ano,
        )
    )
    return int(maximo or 0) + 1


def modelo_para(organizacao_id: int, tipo: str) -> ModeloDocumento | None:
    return db.session.scalar(
        select(ModeloDocumento).where(
            ModeloDocumento.organizacao_id == organizacao_id,
            ModeloDocumento.tipo == tipo,
            ModeloDocumento.ativo.is_(True),
        )
    )


def renderizar_html(modelo_html: str, contexto: dict[str, Any]) -> str:
    """Renderiza o template editável em ambiente sandbox (sem SSTI)."""
    try:
        return _SANDBOX.from_string(modelo_html).render(**contexto)
    except Exception as exc:  # template malformado pela organização
        raise ErroDocumento(f"Falha ao renderizar o modelo: {exc}") from exc


def _gerar_pdf(html: str) -> bytes | None:
    """Retorna bytes de PDF se o WeasyPrint estiver disponível; senão ``None``."""
    try:
        from weasyprint import HTML  # import tardio: dependência opcional
    except Exception:
        return None
    return HTML(string=html).write_pdf()


def pdf_disponivel() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:
        return False


def emitir(
    organizacao_id: int,
    *,
    tipo: str,
    contexto: dict[str, Any],
    setor_origem_id: int | None = None,
    setor_destino_id: int | None = None,
    data: date | None = None,
    emitido_por_id: int | None = None,
    assinado_por: str | None = None,
    movimentacao: Movimentacao | None = None,
    commit: bool = True,
) -> Documento:
    if tipo not in TIPOS_DOCUMENTO:
        raise ErroDocumento(f"Tipo de documento inválido: {tipo}.")

    data = data or date.today()
    ano = data.year
    seq = proximo_sequencial(organizacao_id, tipo, ano)
    numero = f"{tipo}-{ano}-{seq:06d}"

    org = db.session.get(Organizacao, organizacao_id)
    modelo = modelo_para(organizacao_id, tipo)
    modelo_html = modelo.conteudo_html if modelo else MODELO_PADRAO

    snapshot = _jsonable(
        {
            "documento": {
                "numero": numero,
                "data": data.isoformat(),
                "tipo": tipo,
                "rotulo_tipo": ROTULO_DOCUMENTO.get(tipo, tipo),
            },
            "organizacao": {"nome": getattr(org, "nome", ""), "cnpj": getattr(org, "cnpj", None)},
            **contexto,
        }
    )

    html = renderizar_html(modelo_html, snapshot)
    pdf = _gerar_pdf(html)
    if pdf is not None:
        conteudo, formato, ext = pdf, "pdf", ".pdf"
    else:
        conteudo, formato, ext = html.encode("utf-8"), "html", ".html"

    digest = hashlib.sha256(conteudo).hexdigest()
    nome_arquivo = f"{secrets.token_hex(8)}{ext}"
    (_dir() / nome_arquivo).write_bytes(conteudo)
    nome_rel = f"documentos/{nome_arquivo}"

    doc = Documento(
        organizacao_id=organizacao_id,
        tipo=tipo,
        sequencial=seq,
        ano=ano,
        numero=numero,
        data=data,
        setor_origem_id=setor_origem_id,
        setor_destino_id=setor_destino_id,
        modelo_id=modelo.id if modelo else None,
        emitido_por_id=emitido_por_id,
        arquivo=nome_rel,
        formato=formato,
        hash=digest,
        assinado_por=assinado_por,
        dados=snapshot,
    )
    db.session.add(doc)
    db.session.flush()
    if movimentacao is not None:
        movimentacao.documento_id = doc.id
    if commit:
        db.session.commit()
    return doc


def caminho_arquivo(doc: Documento) -> Path | None:
    if not doc.arquivo:
        return None
    return Path(current_app.config["UPLOAD_DIR"]) / doc.arquivo


# Mapa Movimentacao.tipo -> tipo de Documento.
MOV_PARA_DOC = {
    "SAIDA": "SAIDA",
    "ENTRADA": "RECEBIMENTO",
    "DEVOLUCAO": "DEVOLUCAO",
    "TRANSFERENCIA": "TRANSFERENCIA",
    "BAIXA": "BAIXA",
    "EMPRESTIMO": "TERMO_RESPONSABILIDADE",
    "AJUSTE_INVENTARIO": "INVENTARIO",
}


def emitir_de_movimentacao(
    movimentacao: Movimentacao, *, emitido_por_id: int | None = None, commit: bool = True
) -> Documento:
    """Emite o documento correspondente a uma movimentação e o vincula a ela."""
    tipo = MOV_PARA_DOC.get(movimentacao.tipo)
    if tipo is None:
        raise ErroDocumento("Esta movimentação não gera documento.")

    item = movimentacao.produto.nome if movimentacao.produto else "Item"
    contexto = {
        "origem": movimentacao.origem.nome if movimentacao.origem else None,
        "destino": movimentacao.destino.nome if movimentacao.destino else None,
        "destinatario": movimentacao.destinatario,
        "observacoes": movimentacao.observacoes,
        "itens": [{"descricao": item, "quantidade": movimentacao.quantidade}],
    }
    return emitir(
        movimentacao.organizacao_id,
        tipo=tipo,
        contexto=contexto,
        setor_origem_id=movimentacao.origem_setor_id,
        setor_destino_id=movimentacao.destino_setor_id,
        emitido_por_id=emitido_por_id,
        movimentacao=movimentacao,
        commit=commit,
    )
