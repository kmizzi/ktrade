"""
FastAPI application factory for KTrade dashboard.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.web.dependencies import get_db_session
from src.web.routers import dashboard, portfolio, trades, positions, signals, strategies, risk, watchlist, sentiment, grid

# Template and static file paths
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="KTrade Dashboard",
        description="Trading bot dashboard with real-time monitoring",
        version="2.0.0",
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Include routers
    app.include_router(dashboard.router, tags=["Dashboard"])
    app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
    app.include_router(trades.router, prefix="/api/v1/trades", tags=["Trades"])
    app.include_router(positions.router, prefix="/api/v1/positions", tags=["Positions"])
    app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
    app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["Strategies"])
    app.include_router(risk.router, prefix="/api/v1/risk", tags=["Risk"])
    app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["Watchlist"])
    app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment"])
    app.include_router(grid.router, prefix="/api/v1/grid", tags=["Grid Trading"])

    return app


# Create app instance
app = create_app()

# Jinja2 templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def friendly_time(value, show_date=True):
    """
    Convert ISO timestamp to friendly format in PST.
    Example: "Sunday, Dec 21 @ 4:26 PM PST"
    """
    if not value:
        return "--"

    try:
        # Parse the timestamp
        if isinstance(value, str):
            # Handle ISO format strings
            value = value.replace("Z", "+00:00")
            if "+" not in value and len(value) == 19:
                # Assume UTC if no timezone
                dt = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(value)
        elif isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            return str(value)

        # Convert to PST (UTC-8)
        pst = timezone(timedelta(hours=-8))
        dt_pst = dt.astimezone(pst)

        if show_date:
            # Full format: "Sunday, Dec 21 @ 4:26 PM PST"
            return dt_pst.strftime("%A, %b %d @ %-I:%M %p PST")
        else:
            # Time only: "4:26 PM PST"
            return dt_pst.strftime("%-I:%M %p PST")
    except Exception:
        return str(value)[:16] if value else "--"


# Register custom filters
templates.env.filters["friendly_time"] = friendly_time


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ktrade-dashboard"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)
