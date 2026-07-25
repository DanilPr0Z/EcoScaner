#!/usr/bin/env bash
# Запуск бэкенда в контейнере.
set -euo pipefail

# Схему ведёт Alembic, а не create_all: в проде нужно видеть, что именно
# меняется в базе, и уметь откатиться.
echo "Применяем миграции…"
alembic upgrade head

# Модель включена, но весов нет — это остановит контейнер сразу, а не при
# первом сканировании, когда ошибку увидит уже пользователь.
#
# Путей может быть несколько через запятую: ответы моделей усредняются.
# Проверяем каждый — иначе строка «a.pt,b.pt» просто не найдётся как файл,
# и понять из сообщения, какого именно файла не хватает, будет нельзя.
if [ "${CLASSIFIER:-stub}" = "ml" ]; then
  IFS=','
  for weights in ${WASTE_CLASSIFIER_WEIGHTS:-prediction/waste_classifier.pt}; do
    if [ ! -f "$weights" ]; then
      echo "CLASSIFIER=ml, но файла весов нет: $weights" >&2
      echo "Скопируйте его на сервер (см. deploy/README.md) или поставьте CLASSIFIER=stub." >&2
      exit 1
    fi
  done
  unset IFS
fi

# Один воркер: модель занимает около гигабайта, и каждый следующий воркер
# поднимет её копию. Для нагрузки хакатона одного достаточно, инференс и так
# уходит в отдельный поток.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips '*'
