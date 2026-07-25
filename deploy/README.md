# Выкладка на VDS с Ubuntu 22.04

Приложение поднимается двумя контейнерами: `api` — FastAPI с моделью, `web` —
nginx, который отдаёт собранный фронтенд и проксирует на бэкенд `/api`
и `/static`. Браузер видит один источник, поэтому CORS в проде не участвует.

## Что понадобится

* VDS с Ubuntu 22.04, **минимум 2 ГБ памяти и 10 ГБ диска** — образ с torch
  занимает около полутора гигабайт, сама модель держит в памяти ещё гигабайт.
  На 1 ГБ сборка не пройдёт.
* Доступ по SSH и права sudo.

## 1. Docker

```bash
sudo apt update && sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
```

## 2. Код и настройки

```bash
git clone https://github.com/DanilPr0Z/EcoScaner.git
cd EcoScaner
cp deploy/.env.production.example .env.production
```

Файл `.env.production` при необходимости поправьте — по умолчанию он готов
к работе.

## 3. Веса модели

Обученная модель в репозитории не хранится: она весит десять мегабайт
и меняется после каждого переобучения. Скопируйте её со своей машины:

```bash
# выполняется локально, не на сервере
scp prediction/waste_classifier.pt user@СЕРВЕР:~/EcoScaner/prediction/
```

Без этого файла контейнер не запустится и скажет об этом прямо. Если модель
пока не нужна, поставьте в `.env.production` строку `CLASSIFIER=stub`.

## 4. Запуск

```bash
docker compose up -d --build
```

Первая сборка занимает 10–20 минут: ставится torch. Дальше — меньше минуты.

```bash
docker compose ps                 # состояние
docker compose logs -f api        # логи бэкенда
curl localhost/api/v1/health      # проверка
```

Приложение доступно на `http://АДРЕС_СЕРВЕРА`.

## 5. Файрвол

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw --force enable
```

## Обновление

```bash
git pull
docker compose up -d --build
```

Новая модель после переобучения — без пересборки образа:

```bash
scp prediction/waste_classifier.pt user@СЕРВЕР:~/EcoScaner/prediction/
ssh user@СЕРВЕР 'cd EcoScaner && docker compose restart api'
```

## Данные

База и снимки пользователей лежат в томе `bingo-data` и переживают пересборку.
Резервная копия:

```bash
docker run --rm -v ecoscaner_bingo-data:/data -v $PWD:/backup alpine \
  tar czf /backup/bingo-backup.tar.gz -C /data .
```

Забрать исправления пользователей для дообучения:

```bash
docker compose cp api:/data/uploads ./storage/uploads
docker compose cp api:/data/bingo.db ./bingo.db
python -m prediction.export_feedback
```

## Домен и HTTPS

Пока сервис работает по HTTP на голом адресе. Для домена с сертификатом
проще всего добавить перед `web` любой обратный прокси с автоматическим
Let's Encrypt (Caddy, nginx-proxy + acme-companion) — трогать конфигурацию
самого приложения не нужно, оно уже слушает 80 порт внутри сети Docker.

**Важно:** камера в браузере работает только по HTTPS или на localhost.
На голом IP по HTTP кнопка «Снять на камеру» не заработает — загрузка файлом
и вставка из буфера будут работать как обычно.

## Если что-то пошло не так

| Симптом | Причина |
|---|---|
| Сборка падает без сообщения | Не хватило памяти. Нужно 2 ГБ, помогает временный swap |
| `api` перезапускается по кругу | Нет файла весов, а `CLASSIFIER=ml`. Смотрите `docker compose logs api` |
| 413 при загрузке фото | Файл больше 10 МБ |
| Камера не открывается | Нужен HTTPS, см. выше |
| Первый скан идёт долго | Модель грузится при старте; `healthcheck` ждёт 90 секунд |
