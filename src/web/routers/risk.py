"""
Risk API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.web.dependencies import get_db_session
from src.web.services.risk_service import RiskService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/metrics", response_class=HTMLResponse)
async def get_metrics(request: Request, db: Session = Depends(get_db_session)):
    """Get risk metrics partial for HTMX."""
    service = RiskService(db)
    metrics = service.get_current_metrics()
    return templates.TemplateResponse(
        "partials/risk_gauges.html",
        {"request": request, **metrics}
    )


@router.get("/checks")
async def get_checks(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get risk check history."""
    service = RiskService(db)
    return service.get_check_history(limit=limit)


@router.get("/rejections")
async def get_rejections(
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get order rejections."""
    service = RiskService(db)
    return service.get_rejections(limit=limit)


@router.get("/limits")
async def get_limits():
    """Get current risk limits from settings."""
    service = RiskService(None)
    return service.get_limits()


@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(30, le=365),
    db: Session = Depends(get_db_session)
):
    """Get daily P&L history."""
    service = RiskService(db)
    return service.get_daily_pnl(days=days)
