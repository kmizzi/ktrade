"""
Trades API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.trade_service import TradeService

router = APIRouter()


def get_templates():
    from src.web.app import templates
    return templates


@router.get("/")
async def get_trades(
    limit: int = Query(50, le=500),
    offset: int = 0,
    strategy: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    sort: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get all trades with optional filters."""
    service = TradeService(db)
    return service.get_trades(
        limit=limit,
        offset=offset,
        strategy=strategy,
        symbol=symbol,
        side=side,
        sort=sort,
        search=q
    )


@router.get("/recent", response_class=HTMLResponse)
async def get_recent_trades(
    request: Request,
    limit: int = Query(50, le=100),
    side: Optional[str] = None,
    symbol: Optional[str] = None,
    sort: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db_session)
):
    """Get recent trades partial for HTMX with filtering."""
    service = TradeService(db)
    trades = service.get_trades(
        limit=limit,
        side=side,
        symbol=symbol,
        sort=sort,
        search=q
    )
    symbols = service.get_unique_symbols()
    return get_templates().TemplateResponse(
        "partials/trades_list.html",
        {
            "request": request,
            "trades": trades,
            "symbols": symbols,
            "current_filters": {
                "side": side,
                "symbol": symbol,
                "sort": sort or "time_desc",
                "q": q
            }
        }
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
