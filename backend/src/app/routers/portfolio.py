from fastapi import APIRouter, HTTPException

from app.deps import PortfolioServiceDep
from app.schemas.portfolio import HoldingCreate, HoldingRead, PortfolioCreate, PortfolioRead

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("/", response_model=list[PortfolioRead])
async def list_portfolios(service: PortfolioServiceDep) -> list:
    return await service.list_portfolios()


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(portfolio_id: int, service: PortfolioServiceDep) -> object:
    portfolio = await service.get_portfolio(portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.post("/", response_model=PortfolioRead, status_code=201)
async def create_portfolio(data: PortfolioCreate, service: PortfolioServiceDep) -> object:
    return await service.create_portfolio(data)


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(portfolio_id: int, service: PortfolioServiceDep) -> None:
    deleted = await service.delete_portfolio(portfolio_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Portfolio not found")


@router.post("/{portfolio_id}/holdings", response_model=HoldingRead, status_code=201)
async def add_holding(
    portfolio_id: int, data: HoldingCreate, service: PortfolioServiceDep
) -> object:
    holding = await service.add_holding(portfolio_id, data)
    if holding is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return holding
