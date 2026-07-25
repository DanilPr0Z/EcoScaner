#!/usr/bin/env bash
# Первоначальная настройка VDS с Ubuntu 22.04.
#
# Ставит Docker, разрешает нужные порты, клонирует репозиторий и готовит
# настройки. Модель копируется отдельно — её нет в репозитории.
#
# Запускать на сервере:
#   curl -fsSL https://raw.githubusercontent.com/DanilPr0Z/EcoScaner/main/deploy/setup-server.sh | bash
#
# Или, если репозиторий уже клонирован:
#   bash deploy/setup-server.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/DanilPr0Z/EcoScaner.git}"
TARGET_DIR="${TARGET_DIR:-$HOME/EcoScaner}"

green() { printf '\033[32m%s\033[0m\n' "$1"; }
dim()   { printf '\033[2m%s\033[0m\n' "$1"; }
red()   { printf '\033[31m%s\033[0m\n' "$1"; }

# Сборка образа с torch не укладывается в гигабайт памяти и падает без
# внятного сообщения. Лучше сказать об этом сразу.
memory_mb=$(free -m | awk '/^Mem:/ {print $2}')
if [ "$memory_mb" -lt 1800 ]; then
  red "На сервере ${memory_mb} МБ памяти, для сборки нужно около 2000."
  red "Добавьте swap или возьмите тариф побольше:"
  red "  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile"
  red "  sudo mkswap /swapfile && sudo swapon /swapfile"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  dim "Ставим Docker…"
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl git
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  green "Docker установлен. После скрипта перелогиньтесь или выполните: newgrp docker"
fi

if [ ! -d "$TARGET_DIR/.git" ]; then
  dim "Клонируем репозиторий в $TARGET_DIR…"
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
else
  dim "Репозиторий уже есть, обновляем…"
  git -C "$TARGET_DIR" pull --ff-only
fi

cd "$TARGET_DIR"

if [ ! -f .env.production ]; then
  cp deploy/.env.production.example .env.production
  green "Создан .env.production — при необходимости поправьте."
fi

if command -v ufw >/dev/null 2>&1; then
  dim "Открываем порты…"
  sudo ufw allow OpenSSH >/dev/null
  sudo ufw allow 80/tcp >/dev/null
  sudo ufw --force enable >/dev/null
fi

echo
if [ -f prediction/waste_classifier.pt ]; then
  green "Всё готово. Запуск:"
  echo "  cd $TARGET_DIR && docker compose up -d --build"
else
  red "Не хватает только модели — её нет в репозитории."
  echo
  echo "Скопируйте её со своей машины:"
  echo "  scp prediction/waste_classifier.pt $USER@$(hostname -I | awk '{print $1}'):$TARGET_DIR/prediction/"
  echo
  echo "После этого:"
  echo "  cd $TARGET_DIR && docker compose up -d --build"
  echo
  dim "Либо поставьте CLASSIFIER=stub в .env.production и поднимайте без модели."
fi
