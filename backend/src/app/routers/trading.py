from fastapi import APIRouter, HTTPException, Query

from app.deps import TradingServiceDep
from app.schemas.trading import OrderCreate, OrderRead

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/orders", response_model=list[OrderRead])
async def list_orders(
    service: TradingServiceDep,
    limit: int = Query(50, ge=1, le=200),
) -> list:
    return await service.list_orders(limit)


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order(order_id: int, service: TradingServiceDep) -> object:
    order = await service.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders", response_model=OrderRead, status_code=201)
async def create_order(data: OrderCreate, service: TradingServiceDep) -> object:
    return await service.create_order(data)
