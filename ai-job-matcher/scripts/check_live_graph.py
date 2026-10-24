"""Live integration smoke: actual Ollama, Qdrant, MCP and SQLite; NO Telegram delivery."""
import logging
import sqlite3
import sys
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from app.agents.llm import StructuredLLM
from app.config import get_settings
from app.graph import build_graph
from app.models import IncomingMessage
from app.services.mcp_fetch import MCPFetcher
from app.services.rag import ResumeRAG


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings().model_copy(update={
        "mcp_fetch_command": sys.executable,
        "mcp_fetch_args": ["-m", "mcp_server_fetch"],
        "mcp_fetch_allowed_domains": "example.com",
    })
    msg = IncomingMessage(
        message_id=1, chat_id=-1001234567,
        message_text="Вакансия: Middle Python Backend Developer. Нужны Python, Django, PostgreSQL, Celery, REST API, Docker. Kubernetes — преимущество.",
        vacancy_url="https://example.com/",
        source_name="Live integration preflight",
    )
    config = {"configurable": {"thread_id": f"live-preflight:{uuid4().hex}"}}
    print("REAL INTEGRATION PREFLIGHT — Telegram delivery disabled", flush=True)
    print("Ollama:", settings.ollama_chat_model, "| Qdrant:", settings.qdrant_collection, flush=True)
    with sqlite3.connect(":memory:", check_same_thread=False) as connection:
        graph = build_graph(StructuredLLM(settings), ResumeRAG(settings), MCPFetcher(settings),
                            settings, SqliteSaver(connection))
        for update in graph.stream({"message": msg.model_dump(mode="json")}, config=config, stream_mode="updates"):
            for node, result in update.items():
                print("[REAL GRAPH]", node, flush=True)
                if node == "mcp_fetch_tool":
                    print("MCP:", result.get("mcp_log", {}).get("status"), flush=True)
                elif node == "python_vacancy_extractor_agent":
                    print("Python vacancies:", len(result.get("python_vacancies", [])),
                          "extractor_error:", bool(result.get("extractor_error")), flush=True)
                elif node == "rag_retrieve":
                    print("Qdrant fragments:", len(result.get("resume_fragments", [])),
                          "retrieval_ok:", result.get("resume_retrieval_ok"), flush=True)
                elif node == "candidate_matcher_agent":
                    match = result.get("matcher_result", {})
                    print("Score:", match.get("score"), "recommended:", match.get("recommended"),
                          "matched_evidence_count:", len(match.get("matched_skill_evidence", {})),
                          "matcher_error:", bool(result.get("matcher_error")), flush=True)
        state = graph.get_state(config)
        print("SQLite checkpoint stored:", bool(state.values and not state.next), flush=True)


if __name__ == "__main__":
    main()
