from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from app.config import Settings
from app.models import IncomingMessage, ExtractedVacancy, MatcherResult, ResumeFragment
from app.agents.matcher import verify_decision
from app.services.memory import History
from app.services.rag import build_rag_query
from app.services.mcp_fetch import validate_public_url
from app.services.telegram_sender import format_notification
import pytest


def test_config_threshold():
    with pytest.raises(Exception):
        Settings(match_threshold=110)


def test_dedupe_persists(tmp_path):
    db = History(tmp_path / "history.sqlite3")
    message = IncomingMessage(chat_id=-100, message_id=1, message_text="Python Developer")
    assert db.accept(message)
    assert not History(tmp_path / "history.sqlite3").accept(message)
    assert len(db.pending()) == 1


def test_threshold_69_70_and_evidence():
    frag = ResumeFragment(point_id="p1", text="Опыт Python и Django в backend")
    for score, recommended in [(69, False), (70, True)]:
        result = MatcherResult(is_vacancy=True, title="Python", score=score,
            matched_skills=["Python", "Kubernetes"], matched_skill_evidence={"Python": "Опыт Python"})
        verified = verify_decision(result, [frag], 70)
        assert verified.recommended is recommended
        assert verified.matched_skills == ["Python"]
    assert not verify_decision(MatcherResult(is_vacancy=True, title="Python", score=99), []).recommended


def test_rag_query_keeps_vacancy_as_requirements():
    q = build_rag_query(ExtractedVacancy(title="Django Developer", vacancy_text="PostgreSQL Kubernetes"))
    assert "Django" in q and "PostgreSQL" in q and "Kubernetes" in q
    assert "Не считай требования вакансии навыками кандидата" in q


def test_private_urls_rejected():
    for url in ["http://127.0.0.1", "file:///etc/passwd", "http://localhost/private",
                "https://169.254.169.254/latest", "https://example.com"]:
        with pytest.raises(ValueError):
            validate_public_url(url)
    assert validate_public_url("https://example.com/vacancy", "example.com") == "https://example.com/vacancy"


def test_telegram_format_no_source_mix():
    message = IncomingMessage(chat_id=-100, message_id=2, source_name="Jobs",
        source_message_url="https://t.me/jobs/2", message_text="Python developer",
        published_at=datetime(2026, 10, 22, 5, 30, tzinfo=timezone.utc))
    result = MatcherResult(is_vacancy=True, title="Python developer", score=70)
    output = format_notification(message, result)
    assert "70%" in output and "https://t.me/jobs/2" in output
    assert "22.10.2026" in output
