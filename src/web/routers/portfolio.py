"""
Portfolio API routes.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.portfolio_service import PortfolioService

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/summary")
async def get_summary(db: Session = Depends(get_db_session)):
    """Get portfolio summary as JSON."""
    service = PortfolioService(db)
    return service.get_summary()


@router.get("/metrics", response_class=HTMLResponse)
async def get_metrics(request: Request, db: Session = Depends(get_db_session)):
    """Get performance metrics partial."""
    service = PortfolioService(db)
    metrics = service.get_performance_metrics()
    return templates.TemplateResponse(
        "partials/performance_metrics.html",
        {"request": request, "metrics": metrics}
    )


@router.get("/snapshots")
async def get_snapshots(
    limit: int = 30,
    db: Session = Depends(get_db_session)
):
    """Get historical portfolio snapshots."""
    service = PortfolioService(db)
    return service.get_snapshots(limit=limit)


@router.get("/exposure")
async def get_exposure(db: Session = Depends(get_db_session)):
    """Get current portfolio exposure breakdown."""
    service = PortfolioService(db)
    return service.get_exposure()
