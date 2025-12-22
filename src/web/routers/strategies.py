"""
Strategies API routes.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.web.dependencies import get_db_session
from src.web.services.trade_service import TradeService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/")
async def list_strategies(db: Session = Depends(get_db_session)):
    """List all strategies."""
    service = TradeService(db)
    return service.get_strategies()


@router.get("/performance", response_class=HTMLResponse)
async def get_performance(request: Request, db: Session = Depends(get_db_session)):
    """Get all strategy performance partial."""
    service = TradeService(db)
    performance = service.get_strategy_performance()
    return templates.TemplateResponse(
        "partials/strategy_cards.html",
        {"request": request, "strategies": performance}
    )


@router.get("/{strategy_name}/performance")
async def get_strategy_performance(strategy_name: str, db: Session = Depends(get_db_session)):
    """Get single strategy performance metrics."""
    service = TradeService(db)
    return service.get_strategy_metrics(strategy_name)


@router.get("/{strategy_name}/trades")
async def get_strategy_trades(strategy_name: str, db: Session = Depends(get_db_session)):
    """Get trades by strategy."""
    service = TradeService(db)
    return service.get_trades(strategy=strategy_name)


@router.get("/comparison")
async def get_comparison(db: Session = Depends(get_db_session)):
    """Get strategy comparison chart data."""
    service = TradeService(db)
    return service.get_strategy_comparison()
