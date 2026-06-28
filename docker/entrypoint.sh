#!/usr/bin/env bash
# Entrypoint do container: espera o banco, aplica migrações e inicia o app.
set -euo pipefail

echo "==> Aguardando o banco de dados..."
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("DATABASE_URL não definido — pulando espera.")
    sys.exit(0)

for tentativa in range(1, 31):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        print("Banco disponível.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"  ({tentativa}/30) ainda indisponível: {exc.__class__.__name__}")
        time.sleep(2)
else:
    print("Banco não respondeu a tempo.")
    sys.exit(1)
PY

echo "==> Aplicando migrações (alembic)..."
flask --app wsgi db upgrade

if [ "${SEED_DEMO:-false}" = "true" ]; then
    echo "==> Semeando dados de demonstração..."
    flask --app wsgi almox seed || true
else
    echo "==> Sincronizando permissões..."
    flask --app wsgi almox sincronizar-permissoes || true
fi

echo "==> Iniciando aplicação: $*"
exec "$@"
