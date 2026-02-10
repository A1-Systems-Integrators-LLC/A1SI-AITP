import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_portfolios(client: AsyncClient):
    # Create
    response = await client.post(
        "/api/portfolios/",
        json={"name": "Test Portfolio", "exchange_id": "binance"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Portfolio"
    portfolio_id = data["id"]

    # List
    response = await client.get("/api/portfolios/")
    assert response.status_code == 200
    assert len(response.json()) == 1

    # Get
    response = await client.get(f"/api/portfolios/{portfolio_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Portfolio"

    # Add holding
    response = await client.post(
        f"/api/portfolios/{portfolio_id}/holdings",
        json={"symbol": "BTC", "amount": 1.5, "avg_buy_price": 50000},
    )
    assert response.status_code == 201
    assert response.json()["symbol"] == "BTC"

    # Delete
    response = await client.delete(f"/api/portfolios/{portfolio_id}")
    assert response.status_code == 204
