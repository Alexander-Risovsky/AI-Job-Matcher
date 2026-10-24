import logging

from telethon import events


logger = logging.getLogger(
    "telegram-reader"
)


def register_live_listener(
    client,
    processor,
):

    @client.on(
        events.NewMessage()
    )
    async def handle_new_message(
        event,
    ):
        try:
            await processor.process(
                event.message
            )

        except Exception:
            logger.exception(
                "Ошибка NewMessage handler | "
                "chat_id=%s | "
                "message_id=%s",
                event.chat_id,
                event.id,
            )

    return handle_new_message