import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import GetForumTopicsRequest


load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_NAME = os.getenv("TG_SESSION", "vacancy_reader")

# ID группы CY iT HR
CHAT_ID = -1001421126432 


client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH,
)


async def main():
    channel = await client.get_input_entity(CHAT_ID)

    result = await client(
        GetForumTopicsRequest(
            peer=channel,
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100,
            q="",
        )
    )

    print("\nТемы:\n")

    for topic in result.topics:
        print(
            f"topic_id={topic.id:<10} "
            f"title={topic.title!r}"
        )


with client:
    client.loop.run_until_complete(main())