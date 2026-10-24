"""Read-only production inbox/decision status without resume text or tokens."""
import sqlite3
from app.config import get_settings


def main():
    path = get_settings().state_db
    if not path.exists():
        print("No history database yet:", path)
        return
    with sqlite3.connect(path) as db:
        print("\nRECENT TELEGRAM MESSAGES")
        for row in db.execute(
            "SELECT chat_id,message_id,status,created_at FROM inbox ORDER BY created_at DESC LIMIT 15"
        ):
            print(f"chat={row[0]} message={row[1]} status={row[2]} received={row[3]}")
        print("\nMATCH DECISIONS")
        for row in db.execute(
            "SELECT chat_id,message_id,vacancy_index,status,json_extract(decision_json,'$.score') "
            "FROM decisions ORDER BY rowid DESC LIMIT 15"
        ):
            print(f"chat={row[0]} message={row[1]} vacancy={row[2]} "
                  f"status={row[3]} score={row[4]}")
    print("\nPersistent SQLite:", path)


if __name__ == "__main__":
    main()
