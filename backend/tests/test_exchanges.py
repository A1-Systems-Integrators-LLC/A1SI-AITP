import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_exchanges(client: AsyncClient):
    response = await client.get("/api/exchanges/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert any(ex["id"] == "binance" for ex in data)
