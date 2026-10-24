import logging

from telethon.tl.functions.messages import (
    ReadDiscussionRequest,
)

from filters import (
    get_topic_id_from_message,
    is_allowed_source,
)
from payloads import (
    build_payload,
)


logger = logging.getLogger(
    "telegram-reader"
)


class MessageProcessor:

    def __init__(
        self,
        n8n_client,
        telegram_client,
    ) -> None:
        self.n8n_client = (
            n8n_client
        )

        self.telegram_client = (
            telegram_client
        )

        # Защита от повторной обработки
        # внутри одного запуска.
        self._processed: set[
            tuple[int, int]
        ] = set()

        self._inflight: set[
            tuple[int, int]
        ] = set()

    async def mark_as_read(
        self,
        message,
        topic_id: int | None,
    ) -> None:
        """
        Помечает сообщение прочитанным
        только после успешной отправки в n8n.

        Для обычных чатов/каналов:
            обычный read acknowledgement.

        Для Telegram Forum Topic:
            помечаем прочитанной только
            конкретную тему.
        """

        chat_id = message.chat_id

        if chat_id is None:
            return

        try:
            # Forum Topic
            if topic_id is not None:
                entity = (
                    await message.get_input_chat()
                )

                await self.telegram_client(
                    ReadDiscussionRequest(
                        peer=entity,
                        msg_id=topic_id,
                        read_max_id=message.id,
                    )
                )

                logger.info(
                    "✓ Topic помечен прочитанным | "
                    "chat_id=%s | "
                    "topic_id=%s | "
                    "max_message_id=%s",
                    chat_id,
                    topic_id,
                    message.id,
                )

                return

            # Обычный канал / группа / чат.
            await message.mark_read()

            logger.info(
                "✓ Сообщение помечено прочитанным | "
                "chat_id=%s | "
                "message_id=%s",
                chat_id,
                message.id,
            )

        except Exception:
            # Ошибка read-status не должна ломать
            # уже успешно обработанную вакансию.
            logger.exception(
                "Не удалось пометить сообщение "
                "прочитанным | "
                "chat_id=%s | "
                "topic_id=%s | "
                "message_id=%s",
                chat_id,
                topic_id,
                message.id,
            )

    async def process(
        self,
        message,
        *,
        topic_id_override:
            int | None = None,
    ) -> bool:

        chat_id = message.chat_id

        if chat_id is None:
            return False

        topic_id = (
            topic_id_override
            if topic_id_override
            is not None
            else
            get_topic_id_from_message(
                message
            )
        )

        if not is_allowed_source(
            chat_id=chat_id,
            topic_id=topic_id,
        ):
            return False

        key = (
            chat_id,
            message.id,
        )

        if (
            key in self._processed
            or key in self._inflight
        ):
            return False

        self._inflight.add(
            key
        )

        try:
            payload = (
                await build_payload(
                    message=message,
                    topic_id=topic_id,
                )
            )

            if payload is None:
                return False

            preview = (
                payload["message_text"]
                [:100]
                .replace(
                    "\n",
                    " ",
                )
            )

            logger.info(
                "Обработка | "
                "chat=%s | "
                "chat_id=%s | "
                "topic_id=%s | "
                "message_id=%s | "
                "text=%r",
                payload[
                    "source_name"
                ],
                chat_id,
                topic_id,
                message.id,
                preview,
            )

            # Сначала обязательно n8n.
            await self.n8n_client.send(
                payload
            )

            logger.info(
                "✓ Отправлено в n8n | "
                "chat=%s | "
                "message_id=%s",
                payload[
                    "source_name"
                ],
                message.id,
            )

            # Только теперь считаем сообщение
            # успешно обработанным.
            self._processed.add(
                key
            )

            # И только после успешного n8n
            # помечаем его прочитанным в Telegram.
            await self.mark_as_read(
                message=message,
                topic_id=topic_id,
            )

            return True

        except Exception:
            logger.exception(
                "Ошибка обработки | "
                "chat_id=%s | "
                "message_id=%s",
                chat_id,
                message.id,
            )

            return False

        finally:
            self._inflight.discard(
                key
            )