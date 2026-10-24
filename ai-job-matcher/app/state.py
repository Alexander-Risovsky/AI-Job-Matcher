"""One message per checkpoint thread, 0..N vacancy iterations in the same thread."""
from typing import Any, TypedDict


class MatcherState(TypedDict, total=False):
    message: dict[str, Any]
    python_vacancies: list[dict[str, Any]]
    extractor_error: str
    mcp_log: dict[str, Any]
    current_index: int
    external_page_text: str
    rag_query: str
    resume_context: str
    resume_fragments: list[dict[str, Any]]
    resume_retrieval_ok: bool
    rag_error: str
    matcher_result: dict[str, Any]
    matcher_error: str
    decisions: list[dict[str, Any]]
    finished: bool
