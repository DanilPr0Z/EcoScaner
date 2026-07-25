#!/usr/bin/env bash
#
# Запускает BinGo целиком: FastAPI на :8000 и React на :5173.
# Зависимости ставятся сами, если их ещё нет. Занятые порты освобождаются —
# прошлый незакрытый запуск гасится автоматически.
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

# Освобождает порт: гасит то, что на нём слушает. Обычно это прошлый запуск,
# который не закрыли — иначе uvicorn или vite молча уедут на другой порт.
#
# -sTCP:LISTEN обязателен: без него lsof отдаёт и клиентов, подключённых к порту,
# и скрипт заодно убивает открытую вкладку браузера.
free_port() {
  local port="$1" label="$2" pids names
  pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
  [ -z "$pids" ] && return 0

  names=$(ps -o comm= -p $pids 2>/dev/null | xargs -n1 basename 2>/dev/null | sort -u | tr '\n' ' ' || true)
  # Скобки обязательны: без них bash читает имя переменной вместе с многоточием.
  dim "Порт $port занят (${names:-неизвестный процесс}) — закрываем старый ${label}…"
  kill $pids 2>/dev/null || true

  for _ in $(seq 1 25); do
    sleep 0.2
    lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return 0
  done

  # По-хорошему не отпустил — добиваем.
  kill -9 $(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true
  sleep 0.5
  if lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    red "Не удалось освободить порт $port. Посмотрите, что там: lsof -i tcp:$port"
    exit 1
  fi
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
  free_port "$BACK_PORT" "бэкенд"
  prepare_backend
  "$VENV/bin/uvicorn" app.main:app --reload --port "$BACK_PORT" &
  PIDS+=($!)
  green "Бэкенд   → http://localhost:$BACK_PORT/docs"
}

start_frontend() {
  free_port "$FRONT_PORT" "фронтенд"
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
