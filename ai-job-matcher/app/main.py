"""HTTP ingestion only acknowledges durable persistence, not AI completion."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Request, status
from app.config import get_settings
from app.models import IncomingMessage, IngestBatch, IngestReceipt
from app.services.memory import History

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from app.agents.llm import StructuredLLM
    from app.services.rag import ResumeRAG
    from app.services.mcp_fetch import MCPFetcher
    from app.services.telegram_sender import TelegramSender
    from app.services.vacancy_pipeline import Pipeline
    from app.graph import build_graph
    import sqlite3
    # Print app graph transitions reliably even when uvicorn configures
    # logging before lifespan. Never enable httpx request URL logging:
    # Bot API URLs contain the bot token.
    app_log = logging.getLogger("app")
    app_log.setLevel(logging.INFO)
    app_log.propagate = False
    if not app_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        app_log.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = app.state.settings
    settings.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = build_graph(StructuredLLM(settings), ResumeRAG(settings), MCPFetcher(settings), settings, checkpointer)
    pipeline = Pipeline(settings, app.state.history, graph, TelegramSender(settings))
    pipeline.start()
    app.state.pipeline = pipeline
    try:
        yield
    finally:
        pipeline.close()
        conn.close()


def create_app(settings=None, run_worker=True):
    app = FastAPI(title="AI Job Matcher LangGraph",
                  lifespan=lifespan if run_worker else None)
    app.state.settings = settings or get_settings()
    app.state.history = History(app.state.settings.state_db)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "ai-job-matcher"}

    @app.post("/vacancies/ingest", response_model=IngestReceipt, status_code=202)
    async def ingest(request: Request, x_ingest_key: str | None = Header(default=None)):
        import hmac
        settings = app.state.settings
        if settings.ingest_api_key and not hmac.compare_digest(x_ingest_key or "", settings.ingest_api_key):
            raise HTTPException(401, "Unauthorized")
        raw = await request.json()
        try:
            messages = IngestBatch.model_validate(raw).vacancies if isinstance(raw, dict) and "vacancies" in raw else [IncomingMessage.model_validate(raw)]
        except Exception as exc:
            raise HTTPException(422, str(exc)[:500])
        counts = IngestReceipt()
        for message in messages:
            if not message.message_text:
                continue
            if app.state.history.accept(message):
                counts.accepted += 1
            else:
                counts.duplicate += 1
        return counts

    return app


app = create_app()
