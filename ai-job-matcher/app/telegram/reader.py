"""Adapter: reuse the existing modular Telethon reader without n8n."""
# This entrypoint uses the sibling telegram_reader package modules via sys.path.
# No existing user reader files are changed.
import asyncio
import logging
import re

from telethon import TelegramClient
from telethon import events

from app.config import get_settings
from app.models import IncomingMessage
from app.services.memory import History
from app.services.telegram_sender import TelegramSender
import httpx

log = logging.getLogger(__name__)


def topic_id_for_message(message):
    reply = message.reply_to
    if reply is None:
        return None
    top = getattr(reply, "reply_to_top_id", None)
    if top is None and getattr(reply, "forum_topic", False):
        top = getattr(reply, "reply_to_msg_id", None)
    return int(top) if top is not None else None


def allowed(settings, chat_id, topic):
    if chat_id in settings.allowed_topics:
        return topic in settings.allowed_topics[chat_id]
    return chat_id in settings.allowed_chat_ids


async def make_payload(msg, topic):
    text = (msg.raw_text or "").strip()
    if not text or msg.chat_id is None:
        return None
    chat = await msg.get_chat()
    name = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(msg.chat_id)
    username = getattr(chat, "username", None)
    message_url = f"https://t.me/{username}/{msg.id}" if username else (
        f"https://t.me/c/{str(msg.chat_id)[4:]}/{msg.id}" if str(msg.chat_id).startswith("-100") else "")
    external = ""
    for found in re.findall(r"https?://[^\s<>\"']+", text, flags=re.I):
        candidate = found.rstrip(".,);]}")
        if not re.match(r"https?://(?:t\\.me|telegram\\.me)/", candidate, re.I):
            external = candidate
            break
    return IncomingMessage(
        chat_id=msg.chat_id, message_id=msg.id, topic_id=topic, message_text=text,
        source_name=name, source_message_url=message_url,
        vacancy_url=external, published_at=msg.date,
    )


async def run_reader():
    from telethon.tl.functions.messages import GetForumTopicsRequest, ReadDiscussionRequest
    settings = get_settings()
    if not settings.tg_api_id or not settings.tg_api_hash:
        raise RuntimeError("TG_API_ID and TG_API_HASH are required")
    client = TelegramClient(settings.tg_session, settings.tg_api_id, settings.tg_api_hash)
    queued = set()
    inflight = set()

    async with httpx.AsyncClient(timeout=30) as http:
        async def submit(msg, override=None):
            if msg.chat_id is None:
                return
            topic = override if override is not None else topic_id_for_message(msg)
            if not allowed(settings, msg.chat_id, topic):
                return
            key = (msg.chat_id, msg.id)
            if key in inflight or key in queued:
                return
            inflight.add(key)
            try:
                payload = await make_payload(msg, topic)
                if payload is None:
                    return
                response = await http.post(settings.telethon_ingest_url,
                    json=payload.model_dump(mode="json"),
                    headers={"X-Ingest-Key": settings.ingest_api_key} if settings.ingest_api_key else {})
                response.raise_for_status()
                if response.status_code != 202:
                    raise RuntimeError("Ingest server did not return durable receipt")
                receipt = response.json()
                log.info("Telethon accepted chat=%s message=%s queued=%s duplicate=%s",
                         msg.chat_id, msg.id, receipt.get("accepted"), receipt.get("duplicate"))
                queued.add(key)
                if topic is not None:
                    await client(ReadDiscussionRequest(peer=await msg.get_input_chat(),
                        msg_id=topic, read_max_id=msg.id))
                else:
                    await msg.mark_read()
            except Exception:
                log.exception("Will retry on next startup/replay: %s", key)
            finally:
                inflight.discard(key)

        @client.on(events.NewMessage())
        async def on_new(event):
            await submit(event.message)

        await client.start()
        async for dialog in client.iter_dialogs():
            if dialog.id not in settings.allowed_chat_ids:
                continue
            if not dialog.unread_count:
                continue
            read_max = getattr(dialog.dialog, "read_inbox_max_id", 0) or 0
            limit = min(dialog.unread_count, settings.max_startup_unread_per_source) if settings.max_startup_unread_per_source > 0 else dialog.unread_count
            messages = [m async for m in client.iter_messages(dialog.entity,
                limit=limit, min_id=read_max if read_max else 0, reverse=bool(read_max))]
            if not read_max:
                messages.reverse()
            for msg in messages:
                await submit(msg)
                await asyncio.sleep(settings.startup_send_delay_seconds)
        for chat_id, allowed_topics in settings.allowed_topics.items():
            entity = await client.get_entity(chat_id)
            topics = await client(GetForumTopicsRequest(peer=entity, offset_date=None,
                offset_id=0, offset_topic=0, limit=100, q=""))
            for topic in topics.topics:
                if topic.id not in allowed_topics or not topic.unread_count:
                    continue
                count = min(topic.unread_count, settings.max_startup_unread_per_source) if settings.max_startup_unread_per_source > 0 else topic.unread_count
                read_max = getattr(topic, "read_inbox_max_id", 0) or 0
                try:
                    msgs = [m async for m in client.iter_messages(entity, reply_to=topic.id,
                        limit=count, min_id=read_max if read_max else 0, reverse=bool(read_max))]
                    if not read_max:
                        msgs.reverse()
                except Exception:
                    log.exception("Failed topic scan topic_id=%s", topic.id)
                    continue
                for msg in msgs:
                    await submit(msg, override=topic.id)
                    await asyncio.sleep(settings.startup_send_delay_seconds)
        log.info("Reader listening")
        await client.run_until_disconnected()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_reader())
