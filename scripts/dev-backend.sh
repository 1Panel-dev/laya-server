#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo 'Missing .env. Copy .env.example to .env and set the administrator password.' >&2
  exit 1
fi
if [ ! -x .venv/bin/uvicorn ]; then
  echo 'Missing .venv. Install the backend dependencies described in README.md.' >&2
  exit 1
fi

set -a
. ./.env
set +a
if [ -z "${LAYA_ADMIN_PASSWORD:-}" ] && [ -z "${LAYA_ADMIN_PASSWORD_HASH:-}" ]; then
  echo 'Set LAYA_ADMIN_PASSWORD or LAYA_ADMIN_PASSWORD_HASH in .env before starting the backend.' >&2
  exit 1
fi

# Vite proxies /internal and /v1 to this backend during local development.
export LAYA_DATABASE_PATH=./data/laya.sqlite3
export LAYA_MODEL_DIR=./models
export LAYA_DEVICE="${LAYA_DEVICE:-cpu}"
export HF_HOME=./models/.cache
export LAYA_FRONTEND_DIR=./frontend/dist

exec .venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend/server
