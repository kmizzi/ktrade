"""
Positions API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.portfolio_service import PortfolioService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/")
async def get_positions(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db_session)
):
    """Get all positions with optional filters."""
    service = PortfolioService(db)
    return service.get_positions(status=status, limit=limit, offset=offset)


@router.get("/open", response_class=HTMLResponse)
async def get_open_positions(request: Request, db: Session = Depends(get_db_session)):
    """Get open positions partial for HTMX."""
    service = PortfolioService(db)
    positions = service.get_open_positions()
    return templates.TemplateResponse(
        "partials/positions_table.html",
        {"request": request, "positions": positions}
    )


@router.get("/closed")
async def get_closed_positions(
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db_session)
):
    """Get closed positions with pagination."""
    service = PortfolioService(db)
    return service.get_positions(status="closed", limit=limit, offset=offset)


@router.get("/{position_id}")
async def get_position(position_id: int, db: Session = Depends(get_db_session)):
    """Get single position detail."""
    service = PortfolioService(db)
    return service.get_position(position_id)


@router.get("/{position_id}/trades")
async def get_position_trades(position_id: int, db: Session = Depends(get_db_session)):
    """Get trades for a specific position."""
    service = PortfolioService(db)
    return service.get_position_trades(position_id)
