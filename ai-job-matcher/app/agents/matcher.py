from app.models import ExtractedVacancy, MatcherResult
from app.agents.prompts import MATCHER_PROMPT


def match_candidate(llm, vacancy: ExtractedVacancy, resume_context: str) -> MatcherResult:
    prompt = MATCHER_PROMPT.format(
        title=vacancy.title, company=vacancy.company, salary=vacancy.salary,
        vacancy_text=vacancy.vacancy_text, resume_context=resume_context,
    )
    prompt += "\nДля каждого matched_skills добавь matched_skill_evidence: объект {навык: точная короткая цитата из фрагмента резюме}. Если нет цитаты — не включай навык."
    return llm.generate(prompt, MatcherResult)


def verify_decision(result: MatcherResult, fragments: list, threshold: int = 70) -> MatcherResult:
    """Never trust LLM recommended or unverifiable skill evidence."""
    valid = {}
    for skill, evidence in result.matched_skill_evidence.items():
        if skill not in result.matched_skills or not evidence.strip():
            continue
        if any(evidence.strip().casefold() in f.text.casefold() for f in fragments):
            valid[skill] = evidence
    result.matched_skills = [name for name in result.matched_skills if name in valid]
    result.matched_skill_evidence = valid
    if not fragments or not result.is_vacancy:
        result.score = 0
    result.recommended = bool(result.is_vacancy and fragments and result.score >= threshold)
    return result
