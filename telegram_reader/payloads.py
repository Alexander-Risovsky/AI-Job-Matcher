import re


def extract_external_url(
    text: str,
) -> str:
    """
    Находит первую внешнюю ссылку.

    t.me игнорируем, чтобы n8n не пытался
    web-парсить Telegram вместо сайта вакансии.
    """

    urls = re.findall(
        r'https?://[^\s<>"\']+',
        text,
        flags=re.IGNORECASE,
    )

    for url in urls:
        url = url.rstrip(
            ".,);]}"
        )

        lower_url = url.lower()

        telegram_prefixes = (
            "https://t.me/",
            "http://t.me/",
            "https://telegram.me/",
            "http://telegram.me/",
        )

        if lower_url.startswith(
            telegram_prefixes
        ):
            continue

        return url

    return ""


def build_message_url(
    chat_id: int,
    username: str | None,
    message_id: int,
) -> str:
    """
    Ссылка на оригинальное сообщение.
    """

    if username:
        return (
            f"https://t.me/"
            f"{username}/"
            f"{message_id}"
        )

    chat_id_string = str(chat_id)

    if chat_id_string.startswith("-100"):
        internal_id = (
            chat_id_string[4:]
        )

        return (
            f"https://t.me/c/"
            f"{internal_id}/"
            f"{message_id}"
        )

    return ""


async def build_payload(
    message,
    topic_id: int | None,
) -> dict | None:
    text = (
        message.raw_text
        or ""
    ).strip()

    if not text:
        return None

    chat_id = message.chat_id

    if chat_id is None:
        return None

    chat = await message.get_chat()

    chat_title = (
        getattr(
            chat,
            "title",
            None,
        )
        or getattr(
            chat,
            "first_name",
            None,
        )
        or str(chat_id)
    )

    username = getattr(
        chat,
        "username",
        None,
    )

    source_message_url = (
        build_message_url(
            chat_id=chat_id,
            username=username,
            message_id=message.id,
        )
    )

    source_url = (
        extract_external_url(
            text
        )
    )

    published_at = None

    if message.date is not None:
        published_at = (
            message.date.isoformat()
        )

    return {
        "message_id": message.id,
        "chat_id": chat_id,
        "topic_id": topic_id,

        "message_text": text,

        "source_name": chat_title,

        "source_url": source_url,

        "source_message_url":
            source_message_url,

        "published_at":
            published_at,
    }