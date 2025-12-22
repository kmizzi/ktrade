"""
Trades API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.trade_service import TradeService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/")
async def get_trades(
    limit: int = Query(50, le=500),
    offset: int = 0,
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get all trades with optional filters."""
    service = TradeService(db)
    return service.get_trades(limit=limit, offset=offset, strategy=strategy, symbol=symbol)


@router.get("/recent", response_class=HTMLResponse)
async def get_recent_trades(
    request: Request,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db_session)
):
    """Get recent trades partial for HTMX."""
    service = TradeService(db)
    trades = service.get_recent_trades(limit=limit)
    return templates.TemplateResponse(
        "partials/trades_table.html",
        {"request": request, "trades": trades}
    )


@router.get("/by-strategy")
async def get_trades_by_strategy(db: Session = Depends(get_db_session)):
    """Get trades grouped by strategy."""
    service = TradeService(db)
    return service.get_trades_by_strategy()


@router.get("/by-symbol")
async def get_trades_by_symbol(db: Session = Depends(get_db_session)):
    """Get trades grouped by symbol."""
    service = TradeService(db)
    return service.get_trades_by_symbol()
