import httpx
from datetime import timezone
from zoneinfo import ZoneInfo


def format_notification(message, decision) -> str:
    result = decision
    published = "неизвестно"
    if message.published_at:
        published = message.published_at.astimezone(ZoneInfo("Asia/Yekaterinburg")).strftime("%d.%m.%Y, %H:%M")
    lines = [
        f"🔥 Вакансия подходит на {result.score}%", "",
        f"{result.title}{' — ' + result.company if result.company else ''}",
        f"Зарплата: {result.salary or 'не указана'}", "",
        "Совпадает:",
        *([f"✅ {s}" for s in result.matched_skills[:24]] or ["— подтверждений нет"]),
        "", "Не хватает:",
        *([f"⚠️ {s}" for s in result.missing_skills[:24]] or ["— не указано"]),
    ]
    if result.critical_mismatches:
        lines.extend(["", "Критичные расхождения:", *[f"❗ {s}" for s in result.critical_mismatches[:24]]])
    lines.extend(["", "Почему:", result.reason[:1100] or "—", "", "──────────────",
                  f"📢 Источник: {message.source_name}", f"🕒 Опубликовано: {published}",
                  "", "📝 Начало сообщения:", message.message_text.replace("\n", " ")[:180] or "—"])
    if message.source_message_url:
        lines.extend(["", f"🔗 {message.source_message_url}"])
    return "\n".join(lines)[:3900]


class TelegramSender:
    def __init__(self, settings):
        self.settings = settings

    def send(self, message, result):
        if not self.settings.tg_bot_token or not self.settings.tg_target_chat_id:
            raise RuntimeError("Telegram Bot API credentials are not configured")
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"https://api.telegram.org/bot{self.settings.tg_bot_token}/sendMessage",
                json={"chat_id": self.settings.tg_target_chat_id,
                      "text": format_notification(message, result),
                      "disable_web_page_preview": True},
            )
            if response.status_code != 200:
                # Never leak bot token embedded in the Bot API URL into logs.
                raise RuntimeError(f"Telegram Bot API HTTP {response.status_code}")
            if not response.json().get("ok"):
                raise RuntimeError("Telegram Bot API did not accept the message")
