"""
Sentiment API routes.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.web.dependencies import get_db_session
from src.web.services.sentiment_service import SentimentService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/market", response_class=HTMLResponse)
async def get_market_sentiment(request: Request, db: Session = Depends(get_db_session)):
    """Get market sentiment partial for HTMX."""
    service = SentimentService(db)
    sentiment = service.get_market_sentiment()
    return templates.TemplateResponse(
        "partials/sentiment_section.html",
        {"request": request, **sentiment}
    )


@router.get("/symbol/{symbol}")
async def get_symbol_sentiment(symbol: str, db: Session = Depends(get_db_session)):
    """Get sentiment for a specific symbol."""
    service = SentimentService(db)
    return service.get_symbol_sentiment(symbol)


@router.get("/news")
async def get_news():
    """Get news headlines."""
    service = SentimentService(None)
    return service.get_news()


@router.get("/wsb")
async def get_wsb():
    """Get WSB trending stocks."""
    service = SentimentService(None)
    return service.get_wsb_trending()


@router.get("/watchlist")
async def get_watchlist_sentiment(db: Session = Depends(get_db_session)):
    """Get sentiment for watchlist symbols."""
    service = SentimentService(db)
    return service.get_watchlist_sentiment()
