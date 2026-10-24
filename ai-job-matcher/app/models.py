"""Stable Pydantic contracts shared by HTTP, graph, storage and tests."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class IncomingMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: int
    chat_id: int
    topic_id: int | None = None
    message_text: str = ""
    source_name: str = "Telegram"
    source_url: str = ""
    source_message_url: str = ""
    vacancy_url: str = ""
    published_at: datetime | None = None

    @field_validator("message_text")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()


class IngestBatch(BaseModel):
    vacancies: list[IncomingMessage]


class ExtractedVacancy(BaseModel):
    title: str = ""
    company: str = ""
    salary: str = ""
    vacancy_text: str = ""

    @field_validator("title", "company", "salary", "vacancy_text")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()


class ExtractorResult(BaseModel):
    python_vacancies: list[ExtractedVacancy] = Field(default_factory=list)


class MatcherResult(BaseModel):
    is_vacancy: StrictBool
    title: str
    company: str = ""
    salary: str = ""
    score: StrictInt = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    critical_mismatches: list[str] = Field(default_factory=list)
    reason: str = ""
    recommended: bool = False
    matched_skill_evidence: dict[str, str] = Field(default_factory=dict)


class ResumeFragment(BaseModel):
    point_id: str
    text: str
    metadata: dict = Field(default_factory=dict)


class MatchDecision(BaseModel):
    vacancy_index: int
    result: MatcherResult
    resume_retrieval_ok: bool
    retrieved_ids: list[str] = Field(default_factory=list)
    notification_status: str = "skipped"
    error: str = ""


class IngestReceipt(BaseModel):
    accepted: int = 0
    duplicate: int = 0
    status: str = "queued"
