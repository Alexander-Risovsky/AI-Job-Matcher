"""Ollama adapter; response is schema-validated with one bounded retry."""
import json
import logging
from pydantic import ValidationError
from langchain_ollama import ChatOllama

log = logging.getLogger(__name__)


class StructuredLLM:
    def __init__(self, settings):
        self.model = ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model,
            temperature=0,
            reasoning=False,
            format="json",
            num_predict=1800,
            timeout=90,
        )

    def generate(self, prompt: str, schema):
        failure = ""
        for attempt in range(2):
            request = prompt if not attempt else (
                prompt + "\n\nПредыдущий ответ был невалиден: " + failure[:400]
                + "\nОтветь заново строго валидным JSON."
            )
            try:
                message = self.model.invoke(request)
                raw = message.content if isinstance(message.content, str) else str(message.content)
                value = schema.model_validate(json.loads(raw))
                return value
            except (ValueError, TypeError, ValidationError) as exc:
                failure = str(exc)
                log.warning("LLM schema invalid attempt=%s: %s", attempt + 1, failure[:250])
        raise ValueError(f"Invalid LLM JSON after two attempts: {failure[:500]}")
