import httpx

from config import settings


class CursorClient:
    def __init__(self):
        self.base_url = settings.cursor_api_base.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.cursor_api_key}",
            "Content-Type": "application/json",
        }

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=120.0) as client:
            url = f"{self.base_url}{path}"
            return await client.request(method, url, headers=self.headers, **kwargs)

    async def create_agent(self, payload: dict) -> dict:
        response = await self.request("POST", "/v1/agents", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_agent(self, agent_id: str) -> dict:
        response = await self.request("GET", f"/v1/agents/{agent_id}")
        response.raise_for_status()
        return response.json()

    async def get_agent_usage(self, agent_id: str, run_id: str | None = None) -> dict:
        path = f"/v1/agents/{agent_id}/usage"
        params = {"runId": run_id} if run_id else None
        response = await self.request("GET", path, params=params)
        response.raise_for_status()
        return response.json()

    async def list_agents(self, limit: int = 20) -> dict:
        response = await self.request("GET", "/v1/agents", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def followup_agent(self, agent_id: str, payload: dict) -> dict:
        response = await self.request("POST", f"/v1/agents/{agent_id}/followup", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_me(self) -> dict:
        response = await self.request("GET", "/v1/me")
        response.raise_for_status()
        return response.json()
