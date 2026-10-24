import asyncio
import logging

from telethon.tl.functions.messages import (
    GetForumTopicsRequest,
)

from config import (
    ALLOWED_CHAT_IDS,
    ALLOWED_TOPICS,
    MAX_STARTUP_UNREAD_PER_SOURCE,
    STARTUP_SEND_DELAY_SECONDS,
)
from filters import (
    get_topic_id_from_message,
)


logger = logging.getLogger(
    "telegram-reader"
)


def get_limit(
    unread_count: int,
) -> int:
    """
    Возвращает количество сообщений,
    которые нужно обработать.

    MAX_STARTUP_UNREAD_PER_SOURCE = 0
    означает без дополнительного ограничения.
    """

    if (
        MAX_STARTUP_UNREAD_PER_SOURCE
        <= 0
    ):
        return unread_count

    return min(
        unread_count,
        MAX_STARTUP_UNREAD_PER_SOURCE,
    )


async def process_regular_chat(
    client,
    processor,
    dialog,
) -> int:

    unread_count = (
        dialog.unread_count
        or 0
    )

    if unread_count <= 0:
        return 0

    limit = get_limit(
        unread_count
    )

    read_max_id = getattr(
        dialog.dialog,
        "read_inbox_max_id",
        0,
    ) or 0

    logger.info(
        "Непрочитанные | "
        "chat=%s | "
        "chat_id=%s | "
        "unread=%s | "
        "read_max_id=%s",
        dialog.name,
        dialog.id,
        unread_count,
        read_max_id,
    )

    processed = 0

    # Если известна граница прочитанного,
    # получаем сообщения после неё
    # в порядке от старых к новым.
    if read_max_id > 0:
        iterator = (
            client.iter_messages(
                dialog.entity,
                min_id=read_max_id,
                limit=limit,
                reverse=True,
            )
        )

    else:
        # Если Telegram не вернул read_max_id,
        # берём последние unread_count сообщений.
        messages = [
            message
            async for message
            in client.iter_messages(
                dialog.entity,
                limit=limit,
            )
        ]

        messages.reverse()

        iterator = (
            _list_to_async_iterator(
                messages
            )
        )

    async for message in iterator:
        success = (
            await processor.process(
                message
            )
        )

        if success:
            processed += 1

            await asyncio.sleep(
                STARTUP_SEND_DELAY_SECONDS
            )

    return processed


async def _list_to_async_iterator(
    items,
):
    for item in items:
        yield item


async def get_forum_topics(
    client,
    entity,
):
    return await client(
        GetForumTopicsRequest(
            peer=entity,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100,
            q="",
        )
    )


async def collect_topic_messages(
    client,
    entity,
    topic_id: int,
    read_max_id: int,
    limit: int,
):
    """
    Пытаемся получить сообщения конкретной
    Telegram Forum Topic.

    Сначала используем thread/reply_to.

    Если Telegram/Telethon не поддержит
    такой запрос для конкретного форума,
    используем fallback.
    """

    try:
        if read_max_id > 0:
            messages = [
                message
                async for message
                in client.iter_messages(
                    entity,
                    reply_to=topic_id,
                    min_id=read_max_id,
                    limit=limit,
                    reverse=True,
                )
            ]

            return messages

        messages = [
            message
            async for message
            in client.iter_messages(
                entity,
                reply_to=topic_id,
                limit=limit,
            )
        ]

        messages.reverse()

        return messages

    except Exception:
        logger.exception(
            "Не удалось получить тему "
            "через reply_to | "
            "topic_id=%s. "
            "Использую fallback.",
            topic_id,
        )

    # FALLBACK.
    #
    # Берём историю группы после read_max_id
    # и оставляем сообщения нужной темы.
    #
    # Делаем запас, потому что между сообщениями
    # нужной темы могут быть сообщения
    # из других topics.
    scan_limit = max(
        limit * 10,
        200,
    )

    if read_max_id > 0:
        iterator = (
            client.iter_messages(
                entity,
                min_id=read_max_id,
                limit=scan_limit,
                reverse=True,
            )
        )
    else:
        items = [
            message
            async for message
            in client.iter_messages(
                entity,
                limit=scan_limit,
            )
        ]

        items.reverse()

        iterator = (
            _list_to_async_iterator(
                items
            )
        )

    result = []

    async for message in iterator:
        message_topic_id = (
            get_topic_id_from_message(
                message
            )
        )

        if (
            message_topic_id
            != topic_id
        ):
            continue

        result.append(
            message
        )

        if len(result) >= limit:
            break

    return result


async def process_forum(
    client,
    processor,
    chat_id: int,
    allowed_topic_ids: set[int],
) -> int:

    entity = await client.get_entity(
        chat_id
    )

    result = await get_forum_topics(
        client,
        entity,
    )

    processed = 0

    for topic in result.topics:

        topic_id = getattr(
            topic,
            "id",
            None,
        )

        if (
            topic_id
            not in allowed_topic_ids
        ):
            continue

        unread_count = getattr(
            topic,
            "unread_count",
            0,
        ) or 0

        if unread_count <= 0:
            continue

        read_max_id = getattr(
            topic,
            "read_inbox_max_id",
            0,
        ) or 0

        title = getattr(
            topic,
            "title",
            str(topic_id),
        )

        limit = get_limit(
            unread_count
        )

        logger.info(
            "Непрочитанная Forum Topic | "
            "chat_id=%s | "
            "topic=%s | "
            "topic_id=%s | "
            "unread=%s | "
            "read_max_id=%s",
            chat_id,
            title,
            topic_id,
            unread_count,
            read_max_id,
        )

        messages = (
            await collect_topic_messages(
                client=client,
                entity=entity,
                topic_id=topic_id,
                read_max_id=read_max_id,
                limit=limit,
            )
        )

        for message in messages:
            success = (
                await processor.process(
                    message,
                    topic_id_override=(
                        topic_id
                    ),
                )
            )

            if success:
                processed += 1

                await asyncio.sleep(
                    STARTUP_SEND_DELAY_SECONDS
                )

    return processed


async def process_startup_unread(
    client,
    processor,
) -> None:

    logger.info(
        "========================================"
    )

    logger.info(
        "Начинаю обработку "
        "непрочитанных сообщений"
    )

    logger.info(
        "========================================"
    )

    dialogs = {}

    async for dialog in (
        client.iter_dialogs()
    ):
        dialogs[
            dialog.id
        ] = dialog

    total_processed = 0

    # --------------------------------------------------------
    # Обычные чаты / каналы
    # --------------------------------------------------------

    for chat_id in sorted(
        ALLOWED_CHAT_IDS
    ):
        dialog = dialogs.get(
            chat_id
        )

        if dialog is None:
            logger.warning(
                "Диалог не найден | "
                "chat_id=%s",
                chat_id,
            )

            continue

        try:
            count = (
                await process_regular_chat(
                    client=client,
                    processor=processor,
                    dialog=dialog,
                )
            )

            total_processed += (
                count
            )

        except Exception:
            logger.exception(
                "Ошибка чтения "
                "непрочитанных | "
                "chat_id=%s",
                chat_id,
            )

    # --------------------------------------------------------
    # Telegram Forums
    # --------------------------------------------------------

    for (
        chat_id,
        allowed_topics,
    ) in ALLOWED_TOPICS.items():

        try:
            count = (
                await process_forum(
                    client=client,
                    processor=processor,
                    chat_id=chat_id,
                    allowed_topic_ids=(
                        allowed_topics
                    ),
                )
            )

            total_processed += (
                count
            )

        except Exception:
            logger.exception(
                "Ошибка чтения Forum | "
                "chat_id=%s",
                chat_id,
            )

    logger.info(
        "========================================"
    )

    logger.info(
        "Непрочитанные обработаны | "
        "отправлено в n8n: %s",
        total_processed,
    )

    logger.info(
        "========================================"
    )