"""
Grid Trading API routes.
"""

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from src.web.dependencies import get_db_session

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


@router.get("/")
async def get_grids(db: Session = Depends(get_db_session)):
    """Get all grid states."""
    # TODO: Implement with GridOrderExecution model
    return {"grids": []}


@router.get("/{symbol}")
async def get_grid(symbol: str, db: Session = Depends(get_db_session)):
    """Get grid state for symbol."""
    # TODO: Implement with GridOrderExecution model
    return {"symbol": symbol, "state": None}


@router.get("/{symbol}/orders")
async def get_grid_orders(
    symbol: str,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db_session)
):
    """Get grid order history."""
    # TODO: Implement with GridOrderExecution model
    return {"orders": []}


@router.get("/{symbol}/profit")
async def get_grid_profit(symbol: str, db: Session = Depends(get_db_session)):
    """Get grid profit history."""
    # TODO: Implement with GridOrderExecution model
    return {"profit": 0, "history": []}
