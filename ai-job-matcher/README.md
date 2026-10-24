# AI Job Matcher — Python / LangGraph (лабораторная на 8 баллов)

Проект работает **напрямую в WSL Ubuntu, без n8n и без контейнеризации Python-приложения**.

Поток обработки:

```text
Telegram-каналы и темы форума (Telethon)
    → FastAPI /vacancies/ingest
    → SQLite: сохранение входящего сообщения и защита от дублей
    → LangGraph
        ├─ MCP Fetch: внешняя страница вакансии (если есть разрешённая ссылка)
        ├─ Agent 1: Python Vacancy Extractor (Ollama qwen3:8b)
        ├─ RAG: nomic-embed-text → Qdrant candidate_profile, Top K=8
        └─ Agent 2: Candidate Matcher (Ollama qwen3:8b)
    → проверка score >= 70
    → Telegram Bot API (если подходящая вакансия)
    → SQLite: история и checkpoints LangGraph
```

**Ollama работает на Windows**, а само приложение запускается в WSL.
Qdrant — отдельный уже настроенный сервис с сохранённой коллекцией
`candidate_profile`; для работы RAG он должен быть доступен по
`QDRANT_URL`. Исходные данные Qdrant не удаляются и не перезаписываются
при запуске приложения.

## 1. Что необходимо

- Windows 11 + WSL Ubuntu, Python 3.11+ (на этом компьютере Python 3.12).
- Работающая Ollama с моделями `qwen3:8b` и `nomic-embed-text:latest`.
- Доступный сервер Qdrant, коллекция `candidate_profile` (768-d Cosine).
- Авторизованная Telethon-сессия и доступ к разрешённым Telegram-чатам.
- Telegram Bot API token и ID целевого чата.
- Python-пакет `mcp-server-fetch`, запускаемый как внешний **существующий** MCP-сервер.

Открой PowerShell Windows и проверь Ollama:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Если Ollama уже отвечает, повторно вызывать `ollama serve` не нужно.

## 2. Подготовка проекта (один раз)

Открой **VS Code → WSL Ubuntu → Terminal** либо обычный WSL-терминал:

```bash
cd ~/projects/n8n/ai-job-matcher

# Если .venv ещё не существует:
python3 -m venv .venv

source .venv/bin/activate
pip install -e '.[dev]'
```

В проекте уже создан файл `.env`. Не перезаписывай его без необходимости:
в нём настроены реальные Telegram-идентификаторы и секреты.
Для нового окружения можно скопировать `.env.example` в `.env` и заполнить
его самостоятельно.

Основные настройки для **запуска непосредственно из WSL**:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text:latest

QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=candidate_profile
RAG_TOP_K=8
MATCH_THRESHOLD=70

MCP_FETCH_COMMAND=.venv/bin/python
MCP_FETCH_ARGS=["-m","mcp_server_fetch"]
# Добавить только реальные проверенные домены внешних страниц вакансий:
MCP_FETCH_ALLOWED_DOMAINS=
```

Для уже авторизованной сессии текущей машины `TG_SESSION` должен указывать
на `../telegram_reader/vacancy_reader` (без расширения `.session`).
Другие параметры `TG_API_ID`, `TG_API_HASH`, `TG_ALLOWED_CHAT_IDS`,
`TG_ALLOWED_TOPICS`, `TG_BOT_TOKEN`, `TG_TARGET_CHAT_ID` берутся из
реального `.env`.

**Важно:** не отправляй и не показывай на видео `.env`, сессионные файлы,
ключи и настоящее резюме.

## 3. Запуск одной командой (рекомендуется)

Сначала убедись, что ранее запущенные экземпляры API и Telegram-reader
остановлены. В одном WSL-терминале:

```bash
cd ~/projects/n8n/ai-job-matcher
source .venv/bin/activate

python -m scripts.start_local --check
python -m scripts.start_local
```

Первая команда проверяет доступность Ollama и Qdrant и завершает работу.
Вторая запускает **два отдельных процесса**:

1. FastAPI + единственный последовательный LangGraph worker.
2. Telethon-reader, который читает разрешённые каналы и темы Telegram.

Все логи видны в этом терминале. Остановить оба процесса: **Ctrl+C**.
Reader использует существующую Telegram-сессию — нельзя параллельно запускать
старый `../telegram_reader/reader.py` с тем же файлом `.session`.

Если пока нужно проверить только API без чтения новых Telegram-сообщений:

```bash
python -m scripts.start_local --api-only
```

## 4. Альтернатива: два терминала VS Code / WSL

Этот режим удобен для записи видео и отладки: у каждого процесса свои логи.

**Терминал 1 — FastAPI и два AI-агента**

```bash
cd ~/projects/n8n/ai-job-matcher
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info
```

**Терминал 2 — Telethon**

```bash
cd ~/projects/n8n/ai-job-matcher
source .venv/bin/activate
python -m app.telegram.reader
```

Не запускай одновременно этот режим и `scripts.start_local`: иначе два
сервера попытаются занять порт `8000`, а два reader-процесса — один Telegram session.

## 5. Интерфейсы в браузере

| Адрес | Для чего нужен |
|---|---|
| [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger UI: интерактивное описание и ручное выполнение API |
| [http://localhost:8000/health](http://localhost:8000/health) | Проверка работы FastAPI |
| [http://localhost:6333/dashboard](http://localhost:6333/dashboard) | Интерфейс Qdrant: коллекция и количество фрагментов резюме |
| Telegram Desktop | Исходные вакансии и уведомления бота с оценкой |

**Swagger UI — интерфейс для HTTP-запросов, а не отдельная веб-панель
управления агентами.** Сами шаги LangGraph и сообщения MCP видны в
терминале по логам `[LangGraph]`, `MCP tool call`, `[Pipeline]` и
`[Telegram]`.

Для ручного запроса открой Swagger UI → `POST /vacancies/ingest` →
`Try it out`, затем используй JSON:

```json
{
  "message_id": 910001,
  "chat_id": -100123456789,
  "message_text": "Ищем Middle Python Backend Developer. Django, PostgreSQL, Celery.",
  "source_name": "Ручная проверка"
}
```

Здесь ID демонстрационные. Используй **новый** `message_id` для нового теста:
повторная пара `(chat_id, message_id)` будет признана дубликатом.
Ответ **HTTP 202** означает, что сообщение сохранено в SQLite, **не**
гарантирует завершённый AI-анализ и отправку.

Вход через Swagger также запускает реальную обработку; если score >= 70,
успешен RAG и Telegram настроен, бот может отправить настоящее уведомление.

## 6. Проверка реальных агентов и памяти

Тесты (без отправки сообщений в Telegram):

```bash
python -m pytest -q
```

Полная интеграционная проверка **Ollama → MCP Fetch → Qdrant →
LangGraph → SQLite**, но без Telegram-доставки:

```bash
python -m scripts.check_live_graph
```

В этом скрипте используется публичная страница `example.com`
для технической проверки MCP, а вакансии и резюме оцениваются
настоящими Ollama и Qdrant. Для итогового видео лабораторной используй
обычное получение реальной вакансии через Telethon.

Чтобы увидеть уже сохранённые результаты в SQLite, открой **ещё один терминал**:

```bash
cd ~/projects/n8n/ai-job-matcher
source .venv/bin/activate
python -m scripts.show_history
```

SQLite хранится в `data/history.sqlite3`, checkpoints LangGraph — в
`data/checkpoints.sqlite3`. Эти файлы сохраняются между перезапусками.

## 7. Обновление резюме

По умолчанию поиск использует существующие фрагменты `candidate_profile`
в Qdrant. Чтобы загрузить новое PDF-резюме:

```bash
python -m scripts.ingest_resume /путь/к/резюме.pdf
```

Не загружай личное резюме в публичный репозиторий. Скрипт не очищает
всю коллекцию Qdrant и не удаляет другие документы.

## 8. Возможные ошибки

- **`ollama serve`: порт 11434 занят** — Ollama уже запущена; проверь `/api/tags`.
- **Connection refused :6333** — сервер Qdrant не запущен либо недоступен.
  Приложение не может выполнять RAG, пока не восстановлено соединение.
- **Connection refused :8000** — FastAPI ещё не запущен.
- **Address already in use :8000** — второй экземпляр API уже работает.
- **Telegram session is locked** — останови другой Telethon-reader,
  использующий ту же сессию.
- **MCP status=failure** — проверь разрешённые домены
  `MCP_FETCH_ALLOWED_DOMAINS`, доступность внешнего URL и инструмент fetch.
- **RAG не вернул резюме** — score не должен превращаться в успешную
  рекомендацию; проверь `candidate_profile`.
- **В Telegram ничего не приходит** — сначала проверь score, затем
  статус решения в `python -m scripts.show_history`, bot token и целевой chat ID.

Подробный сценарий видеозащиты: [VIDEO_PRODUCTION.md](VIDEO_PRODUCTION.md).

Проект выполняет требования уровня **8 баллов**: два последовательных AI-агента,
локальная LLM, RAG, SQLite-память и реальный вызов существующего MCP.
