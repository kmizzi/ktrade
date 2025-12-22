"""
Signals API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.signal_service import SignalService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/")
async def get_signals(
    limit: int = Query(50, le=500),
    offset: int = 0,
    strategy: Optional[str] = None,
    executed: Optional[bool] = None,
    db: Session = Depends(get_db_session)
):
    """Get all signals with optional filters."""
    service = SignalService(db)
    return service.get_signals(limit=limit, offset=offset, strategy=strategy, executed=executed)


@router.get("/recent", response_class=HTMLResponse)
async def get_recent_signals(
    request: Request,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db_session)
):
    """Get recent signals partial for HTMX."""
    service = SignalService(db)
    signals = service.get_recent_signals(limit=limit)
    return templates.TemplateResponse(
        "partials/signals_list.html",
        {"request": request, "signals": signals}
    )


@router.post("/current", response_class=HTMLResponse)
async def generate_current_signals(request: Request, db: Session = Depends(get_db_session)):
    """Generate current trading signals."""
    service = SignalService(db)
    signals = service.generate_current_signals()
    return templates.TemplateResponse(
        "partials/signals_list.html",
        {"request": request, "signals": signals}
    )


@router.get("/executed")
async def get_executed_signals(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get executed signals."""
    service = SignalService(db)
    return service.get_signals(limit=limit, executed=True)


@router.get("/rejected")
async def get_rejected_signals(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get rejected signals with reasons."""
    service = SignalService(db)
    return service.get_rejections(limit=limit)


@router.get("/rejection-stats")
async def get_rejection_stats(db: Session = Depends(get_db_session)):
    """Get rejection reason breakdown."""
    service = SignalService(db)
    return service.get_rejection_stats()
