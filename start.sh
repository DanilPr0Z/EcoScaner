#!/usr/bin/env bash
#
# Запускает BinGo целиком: FastAPI на :8000 и React на :5173.
# Зависимости ставятся сами, если их ещё нет.
#
#   ./start.sh          — запустить оба сервера
#   ./start.sh back     — только бэкенд
#   ./start.sh front    — только фронтенд
#
# Остановить — Ctrl+C: скрипт гасит оба процесса.

set -euo pipefail

cd "$(dirname "$0")"

BACK_PORT=8000
FRONT_PORT=5173
VENV=".venv"
PYTHON="$VENV/bin/python"

TARGET="${1:-all}"

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }
dim()   { printf '\033[2m%s\033[0m\n' "$1"; }

port_busy() {
  lsof -ti tcp:"$1" >/dev/null 2>&1
}

prepare_backend() {
  if [ ! -x "$PYTHON" ]; then
    dim "Создаём виртуальное окружение…"
    python3 -m venv "$VENV"
  fi
  # Ставим зависимости, только если чего-то не хватает — иначе запуск тормозит на ровном месте.
  if ! "$PYTHON" -c "import fastapi, sqlalchemy, aiosqlite, multipart" >/dev/null 2>&1; then
    dim "Ставим зависимости Python…"
    "$PYTHON" -m pip install -q -r requirements.txt
  fi
}

prepare_frontend() {
  if [ ! -d frontend/node_modules ]; then
    dim "Ставим зависимости npm…"
    (cd frontend && npm install)
  fi
}

PIDS=()

shutdown() {
  echo
  dim "Останавливаем…"
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit 0
}
trap shutdown INT TERM

start_backend() {
  if port_busy "$BACK_PORT"; then
    red "Порт $BACK_PORT занят. Освободите его: lsof -ti tcp:$BACK_PORT | xargs kill"
    exit 1
  fi
  prepare_backend
  "$VENV/bin/uvicorn" app.main:app --reload --port "$BACK_PORT" &
  PIDS+=($!)
  green "Бэкенд   → http://localhost:$BACK_PORT/docs"
}

start_frontend() {
  if port_busy "$FRONT_PORT"; then
    red "Порт $FRONT_PORT занят. Освободите его: lsof -ti tcp:$FRONT_PORT | xargs kill"
    exit 1
  fi
  prepare_frontend
  (cd frontend && npm run dev -- --port "$FRONT_PORT") &
  PIDS+=($!)
  green "Фронтенд → http://localhost:$FRONT_PORT"
}

case "$TARGET" in
  back|backend)   start_backend ;;
  front|frontend) start_frontend ;;
  all)            start_backend; start_frontend ;;
  *)              red "Неизвестный режим: $TARGET (ожидается all, back или front)"; exit 1 ;;
esac

echo
dim "Ctrl+C — остановить."
wait
