# Syslog Docker GUI

Минимальный **syslog-сервер на Python** с **веб-интерфейсом** для смены **порта** и **протокола** (UDP или TCP). Веб-слой на **Starlette** + **uvicorn**. Упакован в **Docker**.

## Возможности

- Приём syslog по **UDP** или **TCP** (один активный режим).
- Сохранение настроек в томе `/data` (`config.json`).
- Просмотр сообщений **в реальном времени** по **WebSocket** (`/ws/logs`).
- **Выгрузка буфера** с сервера (`.txt` или JSON) и **очистка буфера** в памяти из веб-интерфейса.
- Опциональная **запись сообщений в файл** с настраиваемым путём (относительно `DATA_DIR` или абсолютный).

## Запуск (Docker Compose)

```bash
docker compose up --build
```

Откройте веб-интерфейс: [http://localhost:8080](http://localhost:8080). Изменения порта, протокола и параметров записи применяются **сами** (отдельная кнопка «Сохранить» не нужна).

По умолчанию syslog слушает **UDP и TCP на порту 5514** внутри контейнера (порт &lt;1024 без root в контейнере недоступен).

### Порт в UI и Docker

Проброс портов в Docker задаётся **при запуске** контейнера (`ports:` / `-p`). Когда в интерфейсе вы меняете порт syslog, процесс внутри контейнера начинает слушать **другой** порт, но Docker по-прежнему пробрасывает только те порты, что указаны в compose / `docker run`.

**Варианты:**

1. **Диапазон в `docker-compose.yml` (уже настроено)** — проброшены **5000–5999** для UDP и TCP, поэтому любой порт syslog из этого диапазона в UI совпадает с портом на хосте без правки compose. Снаружи обращайтесь к тому же номеру (например UI `5600` → `nc … 5600`).

2. **Один конкретный порт** — если нужен только один порт, можно оставить, например, `"5514:5514/udp"` и не менять порт в UI, либо после смены порта в UI добавить строку в `ports:` и пересоздать контейнер.

3. **Linux, без NAT: `network_mode: host`** — тогда контейнер слушает порты **напрямую на хосте**; менять проброс не нужно. Минус: в этом режиме секция `ports:` игнорируется, конфликты портов решаете вы сами.

```yaml
services:
  syslog-gui:
    network_mode: host
    # ...
```

### Тест с хоста (UDP)

На **macOS** у `logger` нет опций `--server` / `--udp` (это другая утилита). Удобно так:

```bash
echo "hello udp" | nc -u -w1 127.0.0.1 5514
```

На **GNU/Linux** при желании можно использовать:

```bash
logger --server 127.0.0.1 --port 5514 --udp "hello udp"
```

### Тест (TCP)

В UI переключите протокол на TCP, сохраните, затем, например:

```bash
echo "hello tcp" | nc -w1 127.0.0.1 5514
```

## Запуск без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Переменные окружения:

| Переменная | Описание | По умолчанию |
|------------|----------|----------------|
| `WEB_PORT` | Порт веб-интерфейса | `8080` |
| `WEB_HOST` | Хост uvicorn | `0.0.0.0` |
| `DATA_DIR` | Каталог с `config.json` | `./data` |
| `CONFIG_FILE` | Имя файла конфигурации в `DATA_DIR` | `config.json` |

## API

- `GET /api/config` — текущие настройки (`listen_port`, `listen_protocol`, `persist_to_file`, `messages_file_path`).
- `POST /api/config` — пример:
  `{"listen_port": 5514, "listen_protocol": "udp", "persist_to_file": true, "messages_file_path": "logs/syslog.log"}`.
  Пустой `messages_file_path` — файл по умолчанию `DATA_DIR/logs/syslog.log`.
- `GET /api/messages?limit=200` — последние сообщения в буфере памяти.
- `GET /api/messages/export?format=txt` или `format=json` — скачать **все** сообщения из буфера (заголовок `Content-Disposition: attachment`).
- `POST /api/messages/clear` — очистить буфер в памяти; клиентам WebSocket уходит `{ "type": "cleared" }` (файл на диске при включённой записи **не** очищается).
- `WS /ws/logs` — поток JSON: сначала `{ "type": "history", "entries": [...] }`, затем `{ "type": "message", "entry": {...} }` для каждой новой записи, при очистке — `{ "type": "cleared" }`.

## Структура

- `app/main.py` — Starlette, раздача UI и API.
- `app/syslog_server.py` — asyncio UDP/TCP приёмник.
- `static/index.html` — интерфейс.
