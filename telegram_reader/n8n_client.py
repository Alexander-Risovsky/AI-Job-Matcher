import httpx

from config import (
    N8N_WEBHOOK_URL,
)


class N8NClient:

    def __init__(self) -> None:
        self._client = (
            httpx.AsyncClient(
                timeout=30.0,
            )
        )

    async def send(
        self,
        payload: dict,
    ) -> None:
        response = (
            await self._client.post(
                N8N_WEBHOOK_URL,
                json=payload,
            )
        )

        response.raise_for_status()

    async def close(
        self,
    ) -> None:
        await self._client.aclose()