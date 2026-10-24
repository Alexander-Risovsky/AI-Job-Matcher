from app.models import ExtractorResult
from app.agents.prompts import EXTRACTOR_PROMPT


def extract_python_vacancies(llm, text: str) -> ExtractorResult:
    result = llm.generate(EXTRACTOR_PROMPT.replace("{text}", text[:25000]), ExtractorResult)
    return ExtractorResult(python_vacancies=[v for v in result.python_vacancies if v.title])
