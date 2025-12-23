"""
Grid Trading API routes and page endpoints.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional

from src.web.dependencies import get_db_session
from src.web.services.grid_service import GridService

router = APIRouter()

# Import templates from app.py to get custom filters (friendly_time, etc.)
def get_templates():
    from src.web.app import templates
    return templates


# ============ Page Routes ============

@router.get("/grid", response_class=HTMLResponse)
async def grid_page(request: Request, db: Session = Depends(get_db_session)):
    """Grid trading page."""
    service = GridService(db)
    summary = service.get_grid_summary()
    grids = service.get_all_grids()
    config = service.get_grid_config()

    return get_templates().TemplateResponse(
        "pages/grid.html",
        {
            "request": request,
            "summary": summary,
            "grids": grids,
            "config": config,
        }
    )


# ============ API Routes ============

@router.get("/api/v1/grid/summary")
async def get_grid_summary(db: Session = Depends(get_db_session)):
    """Get overall grid trading summary."""
    service = GridService(db)
    return service.get_grid_summary()


@router.get("/api/v1/grid/")
async def get_grids(db: Session = Depends(get_db_session)):
    """Get all grid states."""
    service = GridService(db)
    return {"grids": service.get_all_grids()}


@router.get("/api/v1/grid/{symbol}")
async def get_grid(symbol: str, db: Session = Depends(get_db_session)):
    """Get grid state for symbol."""
    service = GridService(db)
    status = service.get_grid_status(symbol)
    if not status:
        return {"symbol": symbol, "state": None, "error": "Grid not found"}
    return {"symbol": symbol, "state": status}


@router.get("/api/v1/grid/{symbol}/orders")
async def get_grid_orders(
    symbol: str,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get grid order history."""
    service = GridService(db)
    return {"orders": service.get_order_history(symbol=symbol, limit=limit)}


@router.get("/api/v1/grid/orders/recent")
async def get_recent_grid_orders(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db_session)
):
    """Get recent grid orders across all symbols."""
    service = GridService(db)
    return {"orders": service.get_order_history(limit=limit)}


@router.get("/api/v1/grid/{symbol}/profit")
async def get_grid_profit(
    symbol: str,
    days: int = Query(30, le=365),
    db: Session = Depends(get_db_session)
):
    """Get grid profit history."""
    service = GridService(db)
    history = service.get_profit_history(symbol=symbol, days=days)
    total_profit = sum(h["profit"] for h in history)
    return {"profit": total_profit, "history": history}


@router.get("/api/v1/grid/config")
async def get_grid_config(db: Session = Depends(get_db_session)):
    """Get grid trading configuration."""
    service = GridService(db)
    return service.get_grid_config()


# ============ Partial Routes (HTMX) ============

@router.get("/partials/grid/summary", response_class=HTMLResponse)
async def grid_summary_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get grid summary partial for HTMX."""
    service = GridService(db)
    summary = service.get_grid_summary()
    return get_templates().TemplateResponse(
        "partials/grid_summary.html",
        {"request": request, "summary": summary}
    )


@router.get("/partials/grid/status", response_class=HTMLResponse)
async def grid_status_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get all grids status partial for HTMX."""
    service = GridService(db)
    grids = service.get_all_grids()
    prices = service.get_current_prices()
    return get_templates().TemplateResponse(
        "partials/grid_status.html",
        {"request": request, "grids": grids, "prices": prices}
    )


@router.get("/partials/grid/{symbol}/detail", response_class=HTMLResponse)
async def grid_detail_partial(
    request: Request,
    symbol: str,
    db: Session = Depends(get_db_session)
):
    """Get detailed grid status partial for HTMX."""
    service = GridService(db)
    grid = service.get_grid_status(symbol)
    prices = service.get_current_prices()
    current_price = prices.get(symbol, 0)
    return get_templates().TemplateResponse(
        "partials/grid_detail.html",
        {"request": request, "grid": grid, "current_price": current_price}
    )


@router.get("/partials/grid/orders", response_class=HTMLResponse)
async def grid_orders_partial(
    request: Request,
    symbol: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db_session)
):
    """Get grid order history partial for HTMX."""
    service = GridService(db)
    orders = service.get_order_history(symbol=symbol, limit=limit)
    return get_templates().TemplateResponse(
        "partials/grid_orders.html",
        {"request": request, "orders": orders}
    )
