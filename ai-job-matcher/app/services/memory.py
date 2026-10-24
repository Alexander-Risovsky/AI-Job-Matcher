"""Durable SQLite inbox/outbox; a receipt means committed, not analyzed."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.models import IncomingMessage


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.setup()

    @contextmanager
    def db(self):
        with sqlite3.connect(self.path, timeout=30) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=30000")
            yield db

    def setup(self):
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS inbox(
                chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, message_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS decisions(
                chat_id INTEGER, message_id INTEGER, vacancy_index INTEGER,
                vacancy_json TEXT NOT NULL, decision_json TEXT NOT NULL,
                status TEXT NOT NULL, sent_at TEXT,
                PRIMARY KEY(chat_id,message_id,vacancy_index))""")
            db.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def accept(self, message: IncomingMessage) -> bool:
        with self.db() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO inbox(chat_id,message_id,payload) VALUES (?,?,?)",
                (message.chat_id, message.message_id, message.model_dump_json()),
            )
            return cursor.rowcount > 0

    def pending(self) -> list[IncomingMessage]:
        with self.db() as db:
            rows = db.execute("SELECT payload FROM inbox WHERE status IN ('pending','processing','retry') ORDER BY created_at,chat_id,message_id").fetchall()
            return [IncomingMessage.model_validate_json(row["payload"]) for row in rows]

    def mark(self, message, status, error=""):
        with self.db() as db:
            db.execute("UPDATE inbox SET status=?,error=? WHERE chat_id=? AND message_id=?",
                       (status, error[:1000], message.chat_id, message.message_id))

    def decision(self, message, idx, vacancy, decision, status):
        with self.db() as db:
            db.execute("""INSERT INTO decisions(chat_id,message_id,vacancy_index,vacancy_json,decision_json,status)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(chat_id,message_id,vacancy_index) DO UPDATE SET
                vacancy_json=excluded.vacancy_json,decision_json=excluded.decision_json,
                status=CASE WHEN decisions.status='sent' THEN 'sent' ELSE excluded.status END""",
                (message.chat_id, message.message_id, idx, vacancy.model_dump_json(), decision.model_dump_json(), status))

    def is_sent(self, message, idx) -> bool:
        with self.db() as db:
            row = db.execute("SELECT status FROM decisions WHERE chat_id=? AND message_id=? AND vacancy_index=?",
                             (message.chat_id, message.message_id, idx)).fetchone()
            return row is not None and row["status"] == "sent"

    def set_sent(self, message, idx):
        with self.db() as db:
            db.execute("UPDATE decisions SET status='sent',sent_at=CURRENT_TIMESTAMP WHERE chat_id=? AND message_id=? AND vacancy_index=?",
                       (message.chat_id, message.message_id, idx))

    def threshold(self, default: int) -> int:
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='threshold'").fetchone()
        return int(row["value"]) if row else default
