"""
Watchlist API routes.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.web.dependencies import get_db_session
from src.web.services.market_service import MarketService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def get_watchlist(request: Request, db: Session = Depends(get_db_session)):
    """Get watchlist with prices partial for HTMX."""
    service = MarketService(db)
    watchlist = service.get_watchlist()
    return templates.TemplateResponse(
        "partials/watchlist_table.html",
        {"request": request, "watchlist": watchlist}
    )


@router.post("/refresh", response_class=HTMLResponse)
async def refresh_watchlist(request: Request, db: Session = Depends(get_db_session)):
    """Refresh watchlist data."""
    service = MarketService(db)
    watchlist = service.refresh_watchlist()
    return templates.TemplateResponse(
        "partials/watchlist_table.html",
        {"request": request, "watchlist": watchlist}
    )


@router.get("/symbols")
async def get_symbols():
    """Get watchlist symbols."""
    service = MarketService(None)
    return service.get_symbols()


@router.get("/{symbol}")
async def get_symbol(symbol: str, db: Session = Depends(get_db_session)):
    """Get single symbol detail."""
    service = MarketService(db)
    return service.get_symbol_detail(symbol)


@router.get("/{symbol}/bars")
async def get_bars(symbol: str, timeframe: str = "1Day", limit: int = 100):
    """Get price bars for symbol."""
    service = MarketService(None)
    return service.get_bars(symbol, timeframe, limit)
