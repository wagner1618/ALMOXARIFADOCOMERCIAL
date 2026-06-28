"""Ponto de entrada WSGI (Gunicorn/Flask).

Uso em desenvolvimento:
    flask --app wsgi run --debug
Uso em produção:
    gunicorn "wsgi:app" -w 4 -b 0.0.0.0:8000
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()
