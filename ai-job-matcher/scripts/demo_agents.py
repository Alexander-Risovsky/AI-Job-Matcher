"""Recordable LangGraph walkthrough.

Default: genuine Ollama qwen3:8b calls for BOTH agents; synthetic resume
fragments stand in for Qdrant until the real collection is available.
No MCP fetch call and no Telegram messages are sent by this demo.

Use --mock-llm ONLY for deterministic tests of graph orchestration.
"""
import argparse
import json
import logging
import sqlite3
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

from app.agents.llm import StructuredLLM
from app.config import get_settings
from app.graph import build_graph
from app.models import (
    ExtractedVacancy,
    ExtractorResult,
    IncomingMessage,
    MatcherResult,
    ResumeFragment,
)

DEMO_MESSAGE = (
    "Вакансии DemoTech:\n"
    "1) Middle Python Backend Developer: Django, PostgreSQL, Celery, Docker, "
    "опыт REST API. Kubernetes будет плюсом.\n"
    "2) Product Designer: Figma, интерфейсы, знание Python будет плюсом.\n"
    "3) Java Backend Developer: Spring Boot, Java, SQL."
)
DEMO_RESUME = (
    "ДЕМОНСТРАЦИОННОЕ РЕЗЮМЕ (не реальные персональные данные). "
    "Разработчик backend. Работал с Python, Django и PostgreSQL. "
    "Разрабатывал REST API, запускал фоновые задачи на Celery. "
    "Использовал Docker и Git в проектах. "
    "Сведения об опыте Kubernetes отсутствуют."
)


class DemoRAG:
    """Explicit RAG stub; cannot be mistaken for a Qdrant query."""
    def retrieve(self, query: str) -> list[ResumeFragment]:
        print("    [DEMO RAG] Qdrant не используется; возвращён тестовый фрагмент.")
        return [ResumeFragment(point_id="DEMO_FRAGMENT_001", text=DEMO_RESUME)]

    def context(self, fragments: list[ResumeFragment]) -> str:
        return "\n\n".join(f"[Фрагмент {f.point_id}]\n{f.text}" for f in fragments)


class NoFetch:
    async def fetch(self, url: str):
        raise RuntimeError("External MCP is not enabled in demo; use a message without URLs.")


class MockLLM:
    """Tests only. Default CLI uses real Ollama instead."""
    def generate(self, prompt, schema):
        if schema is ExtractorResult:
            return ExtractorResult(python_vacancies=[
                ExtractedVacancy(
                    title="Middle Python Backend Developer", company="DemoTech",
                    vacancy_text="Django, PostgreSQL, Celery, Docker, REST API; Kubernetes будет плюсом.",
                ),
            ])
        if schema is MatcherResult:
            return MatcherResult(
                is_vacancy=True, title="Middle Python Backend Developer", company="DemoTech",
                score=80, matched_skills=["Python", "Django"],
                matched_skill_evidence={
                    "Python": "Работал с Python",
                    "Django": "Django и PostgreSQL",
                },
                missing_skills=["Kubernetes"],
                reason="Сопоставлены навыки из тестовых фрагментов резюме.",
            )
        raise TypeError(schema)


def show_update(node: str, values: dict):
    print(f"\n[LANGGRAPH] ▶ {node}", flush=True)
    if node == "normalize":
        print("    Пост прошёл первичный фильтр:", not values.get("finished", False))
    elif node == "mcp_fetch_tool":
        print("    MCP:", values.get("mcp_log", {}).get("status", "not used"))
    elif node == "python_vacancy_extractor_agent":
        vacancies = values.get("python_vacancies", [])
        print("    Python-вакансий:", len(vacancies))
        for i, vacancy in enumerate(vacancies, 1):
            print(f"    {i}. {vacancy.get('title', '')} — {vacancy.get('company', '')}")
        if values.get("extractor_error"):
            print("    ОШИБКА:", values["extractor_error"])
    elif node == "rag_retrieve":
        print("    Контекст получен:", values.get("resume_retrieval_ok"))
        print("    ID фрагментов:", [r["point_id"] for r in values.get("resume_fragments", [])])
    elif node == "candidate_matcher_agent":
        result = values.get("matcher_result", {})
        print("    Score:", result.get("score", 0))
        print("    Подтверждённые навыки:", result.get("matched_skills", []))
        print("    Не хватает:", result.get("missing_skills", []))
        print("    Решение:", "рекомендовать" if result.get("recommended") else "пропустить")
        if values.get("matcher_error"):
            print("    ОШИБКА:", values["matcher_error"])
    elif node == "collect_decision":
        print("    Вакансия обработана, следующий индекс:", values.get("current_index"))
    print(flush=True)


def main():
    parser = argparse.ArgumentParser(description="Visible LangGraph two-agent demonstration")
    parser.add_argument("--thread-id", default=None, help="Stable ID to demonstrate checkpoint persistence")
    parser.add_argument("--checkpoint-db", type=Path, default=Path("data/demo-checkpoints.sqlite3"))
    parser.add_argument("--diagram", action="store_true", help="Print Mermaid source of the graph")
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic fake agents for tests ONLY")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    settings = get_settings()
    db = args.checkpoint_db
    db.parent.mkdir(parents=True, exist_ok=True)
    thread_id = args.thread_id or "demo:" + uuid4().hex[:12]

    print("=" * 68)
    print("AI JOB MATCHER / LANGGRAPH — ДЕМОНСТРАЦИЯ ДВУХ АГЕНТОВ")
    print("LLM:", "MOCK — только тест графа" if args.mock_llm else f"РЕАЛЬНАЯ Ollama: {settings.ollama_chat_model}")
    print("RAG: ТЕСТОВЫЕ ФРАГМЕНТЫ (Qdrant не подключён в этом режиме)")
    print("MCP: НЕ ВЫЗЫВАЕТСЯ; Telegram: НЕ ОТПРАВЛЯЕТСЯ")
    print("SQLite Checkpointer:", db)
    print("thread_id:", thread_id)
    print("=" * 68)

    with sqlite3.connect(db, check_same_thread=False) as connection:
        checkpointer = SqliteSaver(connection)
        llm = MockLLM() if args.mock_llm else StructuredLLM(settings)
        graph = build_graph(llm, DemoRAG(), NoFetch(), settings, checkpointer)
        if args.diagram:
            print("\n--- Mermaid graph ---\n", graph.get_graph().draw_mermaid())
            return

        config = {"configurable": {"thread_id": thread_id}}
        snapshot = graph.get_state(config)
        if snapshot.values and not snapshot.next:
            print("\n[SQLITE] Граф уже выполнен для thread_id; восстановлено состояние из SQLite.")
        else:
            if snapshot.values:
                incoming = None
                print("[SQLITE] Возобновление прерванного графа.")
            else:
                msg = IncomingMessage(chat_id=-100123456, message_id=1,
                    message_text=DEMO_MESSAGE, source_name="DEMO Python Jobs")
                incoming = {"message": msg.model_dump(mode="json")}
                print("\n[INPUT] Telegram-пост (синтетический):\n" + DEMO_MESSAGE, flush=True)
            for update in graph.stream(incoming, config=config, stream_mode="updates"):
                for node, values in update.items():
                    if isinstance(values, dict):
                        show_update(node, values)

        snapshot = graph.get_state(config)
        state = snapshot.values
        print("\n" + "=" * 68)
        print("ФИНАЛЬНЫЕ РЕШЕНИЯ")
        print(json.dumps(state.get("decisions", []), ensure_ascii=False, indent=2))
        print(f"\n[SQLITE] Решений сохранено: {len(state.get('decisions', []))}")
        print("[SQLITE] Граф завершён:", not bool(snapshot.next))
        print("Повторите с --thread-id", thread_id, "для показа сохранённого состояния.")
        print("=" * 68)


if __name__ == "__main__":
    main()
