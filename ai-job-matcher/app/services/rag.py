"""Qdrant compatible with n8n candidate_profile; collection never recreated implicitly."""
import logging
import re
from langchain_ollama import OllamaEmbeddings
from qdrant_client import QdrantClient
from app.models import ExtractedVacancy, ResumeFragment

log = logging.getLogger(__name__)
TECHNOLOGIES = {
    "Python": r"\bpython(?:\s*3(?:\.\d+)?)?\b",
    "Django": r"\bdjango\b",
    "Django REST Framework": r"\b(?:django\s+rest\s+framework|drf)\b",
    "FastAPI": r"\bfastapi\b", "Flask": r"\bflask\b",
    "PostgreSQL": r"\b(?:postgresql|postgres)\b",
    "SQLAlchemy": r"\bsqlalchemy\b", "SQL": r"\bsql\b",
    "Celery": r"\bcelery\b", "Redis": r"\bredis\b",
    "RabbitMQ": r"\brabbitmq\b", "Kafka": r"\bkafka\b",
    "Docker": r"\bdocker\b", "Kubernetes": r"\b(?:kubernetes|k8s)\b",
    "Linux": r"\blinux\b", "Git": r"\bgit\b",
    "AsyncIO": r"\basyncio\b", "Pytest": r"\bpytest\b",
    "AWS": r"\baws\b", "Microservices": r"\b(?:microservices|микросервис[а-я]*)\b",
}


def build_rag_query(vacancy: ExtractedVacancy) -> str:
    text = f"{vacancy.title}\n{vacancy.vacancy_text}"
    tech = [name for name, pattern in TECHNOLOGIES.items() if re.search(pattern, text, re.I)]
    return "\n\n".join(filter(None, [
        "Найди в резюме кандидата реальные подтверждения опыта и навыков по этой Python-вакансии.",
        f"Должность: {vacancy.title or 'Python Developer'}",
        f"Технологии, упомянутые в вакансии: {', '.join(tech)}" if tech else "",
        f"Требования и обязанности из текста вакансии:\n{vacancy.vacancy_text[:3000]}",
        "Верни релевантные фрагменты реального резюме для сравнения. Не считай требования вакансии навыками кандидата.",
    ]))


class ResumeRAG:
    def __init__(self, settings):
        self.settings = settings
        self.client = QdrantClient(url=settings.qdrant_url, timeout=15)
        self.embedder = OllamaEmbeddings(model=settings.ollama_embed_model, base_url=settings.ollama_base_url)

    def retrieve(self, query: str) -> list[ResumeFragment]:
        collection = self.client.get_collection(self.settings.qdrant_collection)
        vectors = collection.config.params.vectors
        vector_size = getattr(vectors, "size", None)
        if vector_size is not None and vector_size != self.settings.qdrant_vector_size:
            raise ValueError(f"Qdrant vector dimension mismatch: {vector_size}")
        query_vector = self.embedder.embed_query(query)
        if len(query_vector) != self.settings.qdrant_vector_size:
            raise ValueError(f"Embedding size mismatch: {len(query_vector)}")
        result = self.client.query_points(
            collection_name=self.settings.qdrant_collection, query=query_vector,
            limit=self.settings.rag_top_k, with_payload=True,
        ).points
        seen = set()
        fragments = []
        for point in result:
            payload = point.payload or {}
            text = next((str(payload[key]) for key in ("page_content", "pageContent", "text", "content")
                         if isinstance(payload.get(key), str) and payload[key].strip()), "")
            if not text or text in seen:
                continue
            seen.add(text)
            fragments.append(ResumeFragment(point_id=str(point.id), text=text, metadata=payload.get("metadata") or {}))
        return fragments

    def context(self, fragments: list[ResumeFragment]) -> str:
        return "\n\n---\n\n".join(
            f"[Фрагмент резюме {i} | ID: {f.point_id}]\n{f.text}"
            for i, f in enumerate(fragments, 1)
        )[:self.settings.retrieval_context_limit]
