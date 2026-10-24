import asyncio
import logging

from telethon import (
    TelegramClient,
)

from config import (
    ALLOWED_CHAT_IDS,
    ALLOWED_TOPICS,
    N8N_WEBHOOK_URL,
    TG_API_HASH,
    TG_API_ID,
    TG_SESSION,
)
from listener import (
    register_live_listener,
)
from n8n_client import (
    N8NClient,
)
from processor import (
    MessageProcessor,
)
from unread_reader import (
    process_startup_unread,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "telegram-reader"
)


async def print_configuration(
    client,
) -> None:

    me = await client.get_me()

    logger.info(
        "========================================"
    )

    logger.info(
        "Telegram Vacancy Reader"
    )

    logger.info(
        "Авторизован как: %s | "
        "user_id=%s",
        me.first_name,
        me.id,
    )

    logger.info(
        "Webhook: %s",
        N8N_WEBHOOK_URL,
    )

    logger.info(
        "Обычных чатов/каналов: %s",
        len(
            ALLOWED_CHAT_IDS
        ),
    )

    logger.info(
        "Forum-групп: %s",
        len(
            ALLOWED_TOPICS
        ),
    )

    for (
        chat_id,
        topics,
    ) in ALLOWED_TOPICS.items():

        logger.info(
            "FORUM | "
            "chat_id=%s | "
            "topics=%s",
            chat_id,
            sorted(topics),
        )

    overlap = (
        ALLOWED_CHAT_IDS
        & set(
            ALLOWED_TOPICS.keys()
        )
    )

    if overlap:
        logger.warning(
            "Forum chat_id одновременно "
            "находятся в ALLOWED_CHAT_IDS: %s",
            sorted(overlap),
        )

    logger.info(
        "========================================"
    )


async def main() -> None:

    client = TelegramClient(
        TG_SESSION,
        TG_API_ID,
        TG_API_HASH,
    )

    n8n_client = (
        N8NClient()
    )

    processor = MessageProcessor(
        n8n_client=n8n_client,
        telegram_client=client,
    )

    try:
        await client.start()

        await print_configuration(
            client
        )

        # Listener регистрируем ДО чтения
        # старых сообщений.
        #
        # Поэтому сообщения, которые придут
        # во время startup scan, не потеряются.
        register_live_listener(
            client=client,
            processor=processor,
        )

        # Сначала разбираем всё,
        # что Telegram считает непрочитанным.
        await process_startup_unread(
            client=client,
            processor=processor,
        )

        logger.info(
            "Startup scan завершён"
        )

        logger.info(
            "Перехожу в режим "
            "реального времени"
        )

        logger.info(
            "Ожидание новых сообщений..."
        )

        await (
            client
            .run_until_disconnected()
        )

    finally:
        await n8n_client.close()

        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(
        main()
    )