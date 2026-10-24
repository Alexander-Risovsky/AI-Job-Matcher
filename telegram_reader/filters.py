from config import (
    ALLOWED_CHAT_IDS,
    ALLOWED_TOPICS,
)


def get_topic_id_from_message(
    message,
) -> int | None:
    """
    Определяет Telegram Forum topic_id.

    Для обычного канала или группы
    возвращает None.
    """

    reply_to = message.reply_to

    if reply_to is None:
        return None

    topic_id = getattr(
        reply_to,
        "reply_to_top_id",
        None,
    )

    if topic_id is not None:
        return int(topic_id)

    if getattr(
        reply_to,
        "forum_topic",
        False,
    ):
        topic_id = getattr(
            reply_to,
            "reply_to_msg_id",
            None,
        )

        if topic_id is not None:
            return int(topic_id)

    return None


def is_allowed_source(
    chat_id: int,
    topic_id: int | None,
) -> bool:
    """
    Forum:
        chat_id + topic_id.

    Обычный канал/группа:
        только chat_id.
    """

    if chat_id in ALLOWED_TOPICS:
        return (
            topic_id is not None
            and topic_id
            in ALLOWED_TOPICS[chat_id]
        )

    return chat_id in ALLOWED_CHAT_IDS