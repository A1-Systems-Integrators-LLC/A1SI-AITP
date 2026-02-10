from fastapi import APIRouter

from app.deps import ExchangeServiceDep
from app.schemas.exchange import ExchangeInfo

router = APIRouter(prefix="/exchanges", tags=["exchanges"])


@router.get("/", response_model=list[ExchangeInfo])
async def list_exchanges(exchange: ExchangeServiceDep) -> list[ExchangeInfo]:
    return exchange.list_exchanges()
