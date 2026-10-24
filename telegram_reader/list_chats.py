import os

from dotenv import load_dotenv
from telethon import TelegramClient


load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_NAME = os.getenv("TG_SESSION", "vacancy_reader")


client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH,
)


async def main():
    me = await client.get_me()

    print(f"\nАвторизован как: {me.first_name}\n")
    print("Доступные чаты и каналы:")
    print("-" * 100)

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        username = getattr(entity, "username", None)

        print(
            f"ID: {dialog.id:<20} "
            f"Название: {dialog.name!r:<45} "
            f"username: @{username if username else '-'}"
        )


with client:
    client.loop.run_until_complete(main())