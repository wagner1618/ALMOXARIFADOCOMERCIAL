"""Utilitário de upload seguro de arquivos."""

from __future__ import annotations

import secrets
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
EXTENSOES_DOCUMENTO = {".pdf", ".xml", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".xlsx"}


class ErroUpload(Exception):
    """Erro de validação de upload."""


def salvar_arquivo(
    arquivo: FileStorage,
    *,
    subdir: str = "geral",
    extensoes_permitidas: set[str] | None = None,
) -> str:
    """Salva o arquivo com nome saneado e único. Retorna o caminho relativo."""
    if not arquivo or not arquivo.filename:
        raise ErroUpload("Nenhum arquivo enviado.")

    nome_seguro = secure_filename(arquivo.filename)
    extensao = Path(nome_seguro).suffix.lower()
    permitidas = extensoes_permitidas or EXTENSOES_DOCUMENTO
    if extensao not in permitidas:
        raise ErroUpload(f"Tipo de arquivo não permitido: {extensao or '(sem extensão)'}")

    destino_dir = Path(current_app.config["UPLOAD_DIR"]) / subdir
    destino_dir.mkdir(parents=True, exist_ok=True)

    nome_final = f"{secrets.token_hex(8)}{extensao}"
    arquivo.save(str(destino_dir / nome_final))
    return f"{subdir}/{nome_final}"
