import json
import os

from dotenv import load_dotenv


load_dotenv()


TG_API_ID = int(os.environ["TG_API_ID"])
TG_API_HASH = os.environ["TG_API_HASH"]

TG_SESSION = os.getenv(
    "TG_SESSION",
    "vacancy_reader",
)

N8N_WEBHOOK_URL = os.environ[
    "N8N_WEBHOOK_URL"
]


def parse_chat_ids(
    value: str,
) -> set[int]:
    return {
        int(chat_id.strip())
        for chat_id in value.split(",")
        if chat_id.strip()
    }


ALLOWED_CHAT_IDS = parse_chat_ids(
    os.getenv(
        "ALLOWED_CHAT_IDS",
        "",
    )
)


_raw_topics = json.loads(
    os.getenv(
        "ALLOWED_TOPICS_JSON",
        "{}",
    )
)

ALLOWED_TOPICS: dict[int, set[int]] = {
    int(chat_id): {
        int(topic_id)
        for topic_id in topic_ids
    }
    for chat_id, topic_ids
    in _raw_topics.items()
}


# 0 = обработать все непрочитанные.
#
# Например 100:
# максимум 100 непрочитанных сообщений
# на один источник при старте.
MAX_STARTUP_UNREAD_PER_SOURCE = int(
    os.getenv(
        "MAX_STARTUP_UNREAD_PER_SOURCE",
        "0",
    )
)


# Пауза между отправкой старых сообщений в n8n.
#
# Нужна, чтобы при наличии сотен непрочитанных
# не запустить сотни LLM execution одновременно.
STARTUP_SEND_DELAY_SECONDS = float(
    os.getenv(
        "STARTUP_SEND_DELAY_SECONDS",
        "1",
    )
)