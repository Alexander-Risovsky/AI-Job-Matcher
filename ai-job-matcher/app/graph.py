"""Two explicitly distinguished sequential AI agents; other nodes are ordinary tools."""
import asyncio
import logging
from langgraph.graph import StateGraph, START, END
from app.models import IncomingMessage, ExtractedVacancy, ExtractorResult, MatcherResult, ResumeFragment
from app.state import MatcherState
from app.agents.extractor import extract_python_vacancies
from app.agents.matcher import match_candidate, verify_decision
from app.services.rag import build_rag_query
from app.services.mcp_fetch import validate_public_url

log = logging.getLogger(__name__)
VACANCY_HINTS = ("ваканси", "ищем", "требуется", "разработчик", "developer",
                 "engineer", "python", "django", "backend", "frontend", "devops",
                 "аналитик", "зарплат", "salary", "remote", "удален")


def build_graph(llm, rag, fetcher, settings, checkpointer):
    graph = StateGraph(MatcherState)

    def normalize(state):
        msg = IncomingMessage.model_validate(state["message"])
        looks_like = any(hint in msg.message_text.lower() for hint in VACANCY_HINTS)
        log.info("[LangGraph] normalize chat=%s msg=%s accepted=%s", msg.chat_id, msg.message_id, looks_like)
        return {"finished": not looks_like, "current_index": 0, "decisions": []}

    def fetch_url(state):
        msg = IncomingMessage.model_validate(state["message"])
        url = msg.vacancy_url or msg.source_url
        if not url:
            log.info("[LangGraph] mcp_fetch_tool status=not_requested")
            return {"mcp_log": {"status": "not_requested"}, "external_page_text": ""}
        fetched, logdata = asyncio.run(fetcher.fetch(url))
        log.info("[LangGraph] mcp_fetch_tool status=%s text_chars=%s", logdata.get("status"), len(fetched))
        return {"mcp_log": logdata, "external_page_text": fetched}

    def extractor(state):
        msg = IncomingMessage.model_validate(state["message"])
        source = msg.message_text
        if state.get("external_page_text"):
            source += "\n\nТекст со страницы вакансии:\n" + state["external_page_text"]
        try:
            vacancies = extract_python_vacancies(llm, source)
            log.info("[LangGraph] python_vacancy_extractor_agent count=%d", len(vacancies.python_vacancies))
            return {"python_vacancies": [v.model_dump() for v in vacancies.python_vacancies],
                    "extractor_error": "", "finished": not bool(vacancies.python_vacancies),
                    "resume_context": ""}
        except Exception as exc:
            log.exception("Extractor failure")
            return {"python_vacancies": [], "extractor_error": str(exc)[:500], "finished": True,
                    "resume_context": ""}

    def retrieve(state):
        v = ExtractedVacancy.model_validate(state["python_vacancies"][state["current_index"]])
        query = build_rag_query(v)
        try:
            fragments = rag.retrieve(query)
            log.info("[LangGraph] rag_retrieve index=%d fragments=%d", state["current_index"], len(fragments))
            return {"rag_query": query, "resume_fragments": [f.model_dump() for f in fragments],
                    "resume_context": rag.context(fragments), "resume_retrieval_ok": bool(fragments), "rag_error": ""}
        except Exception as exc:
            log.exception("RAG failure")
            return {"rag_query": query, "resume_fragments": [], "resume_context": "",
                    "resume_retrieval_ok": False, "rag_error": str(exc)[:500]}

    def matcher(state):
        v = ExtractedVacancy.model_validate(state["python_vacancies"][state["current_index"]])
        fragments = [ResumeFragment.model_validate(f) for f in state.get("resume_fragments", [])]
        if not fragments:
            result = MatcherResult(is_vacancy=True, title=v.title, company=v.company, salary=v.salary,
                                   score=0, critical_mismatches=["Не удалось получить данные кандидата из RAG"],
                                   reason="Нет проверенных фрагментов резюме")
            return {"matcher_result": result.model_dump(), "matcher_error": ""}
        try:
            result = match_candidate(llm, v, state["resume_context"])
            result = verify_decision(result, fragments, settings.match_threshold)
            log.info("[LangGraph] candidate_matcher_agent index=%d score=%s recommended=%s evidence=%d", state["current_index"], result.score, result.recommended, len(result.matched_skill_evidence))
            return {"matcher_result": result.model_dump(), "matcher_error": ""}
        except Exception as exc:
            log.exception("Matcher failure")
            return {"matcher_result": MatcherResult(
                is_vacancy=True, title=v.title, score=0, reason="LLM failed to provide valid JSON",
                critical_mismatches=["Ошибка Candidate Matcher"]).model_dump(),
                "matcher_error": str(exc)[:500]}

    def collect(state):
        idx = state["current_index"]
        result = state["matcher_result"]
        log.info("[LangGraph] collect_decision index=%d score=%s", idx, result.get("score", 0))
        return {"decisions": state.get("decisions", []) + [{
            "vacancy_index": idx, "result": result, "rag_ok": state.get("resume_retrieval_ok", False),
            "ids": [f["point_id"] for f in state.get("resume_fragments", [])],
            "error": state.get("rag_error", "") or state.get("matcher_error", "")}],
            "current_index": idx + 1}

    def loop(state):
        return "retrieve" if state["current_index"] < len(state.get("python_vacancies", [])) else END

    graph.add_node("normalize", normalize)
    graph.add_node("mcp_fetch_tool", fetch_url)
    graph.add_node("python_vacancy_extractor_agent", extractor)
    graph.add_node("rag_retrieve", retrieve)
    graph.add_node("candidate_matcher_agent", matcher)
    graph.add_node("collect_decision", collect)
    graph.add_edge(START, "normalize")
    graph.add_conditional_edges("normalize", lambda s: END if s["finished"] else "mcp_fetch_tool")
    graph.add_edge("mcp_fetch_tool", "python_vacancy_extractor_agent")
    graph.add_conditional_edges("python_vacancy_extractor_agent", lambda s: END if s["finished"] else "rag_retrieve")
    graph.add_edge("rag_retrieve", "candidate_matcher_agent")
    graph.add_edge("candidate_matcher_agent", "collect_decision")
    graph.add_conditional_edges("collect_decision", loop)
    return graph.compile(checkpointer=checkpointer)
