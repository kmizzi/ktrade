"""
Main dashboard routes.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.web.dependencies import get_db_session
from src.web.services.portfolio_service import PortfolioService
from src.web.services.trade_service import TradeService
from src.web.services.signal_service import SignalService
from src.web.services.risk_service import RiskService
from src.web.services.market_service import MarketService
from src.web.services.sentiment_service import SentimentService
from src.api.alpaca_client import alpaca_client

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


def friendly_time(value, show_date=True):
    """Convert ISO timestamp to friendly format in PST."""
    if not value:
        return "--"
    try:
        if isinstance(value, str):
            value = value.replace("Z", "+00:00")
            if "+" not in value and len(value) >= 19:
                dt = datetime.fromisoformat(value[:19]).replace(tzinfo=timezone.utc)
            else:
                dt = datetime.fromisoformat(value)
        elif isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        else:
            return str(value)
        pst = timezone(timedelta(hours=-8))
        dt_pst = dt.astimezone(pst)
        if show_date:
            return dt_pst.strftime("%A, %b %d @ %-I:%M %p PST")
        return dt_pst.strftime("%-I:%M %p PST")
    except Exception:
        return str(value)[:16] if value else "--"


templates.env.filters["friendly_time"] = friendly_time


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Render main dashboard page."""
    return templates.TemplateResponse(
        "pages/dashboard.html",
        {
            "request": request,
            "title": "KTrade Dashboard",
        }
    )


@router.get("/api/v1/dashboard/summary", response_class=HTMLResponse)
async def dashboard_summary(request: Request, db: Session = Depends(get_db_session)):
    """Get portfolio summary partial for HTMX."""
    try:
        service = PortfolioService(db)
        summary = service.get_summary()
        return templates.TemplateResponse(
            "partials/portfolio_summary.html",
            {"request": request, **summary}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/api/v1/dashboard/equity-chart", response_class=HTMLResponse)
async def equity_chart(request: Request, db: Session = Depends(get_db_session)):
    """Get equity curve chart partial for HTMX."""
    try:
        service = PortfolioService(db)
        chart_data = service.get_equity_curve()
        return templates.TemplateResponse(
            "partials/equity_chart.html",
            {"request": request, "chart_data": chart_data}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/api/v1/dashboard/market-status", response_class=HTMLResponse)
async def market_status(request: Request):
    """Get market status badge."""
    try:
        clock = alpaca_client.get_clock()
        is_open = clock.get("is_open", False)
        return templates.TemplateResponse(
            "components/market_status.html",
            {"request": request, "is_open": is_open}
        )
    except Exception:
        return templates.TemplateResponse(
            "components/market_status.html",
            {"request": request, "is_open": False, "error": True}
        )


# HTMX Partials for dashboard
@router.get("/partials/positions/open", response_class=HTMLResponse)
async def positions_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get open positions partial for HTMX."""
    try:
        service = PortfolioService(db)
        positions = service.get_open_positions()
        return templates.TemplateResponse(
            "partials/positions_list.html",
            {"request": request, "positions": positions}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/signals/recent", response_class=HTMLResponse)
async def signals_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get recent signals partial for HTMX."""
    try:
        service = SignalService(db)
        signals = service.get_recent_signals(limit=5)
        return templates.TemplateResponse(
            "partials/signals_list.html",
            {"request": request, "signals": signals}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.post("/api/v1/signals/generate", response_class=HTMLResponse)
async def generate_signals(request: Request, db: Session = Depends(get_db_session)):
    """Generate new signals and return partial."""
    try:
        service = SignalService(db)
        signals = service.generate_current_signals()
        return templates.TemplateResponse(
            "partials/signals_list.html",
            {"request": request, "signals": signals}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/trades/recent", response_class=HTMLResponse)
async def trades_partial(request: Request, db: Session = Depends(get_db_session), limit: int = 5):
    """Get recent trades partial for HTMX."""
    try:
        service = TradeService(db)
        trades = service.get_recent_trades(limit=limit)
        return templates.TemplateResponse(
            "partials/trades_list.html",
            {"request": request, "trades": trades}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/strategies/summary", response_class=HTMLResponse)
async def strategies_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get strategy performance partial for HTMX."""
    try:
        service = TradeService(db)
        strategies = service.get_strategy_performance()
        return templates.TemplateResponse(
            "partials/strategy_summary.html",
            {"request": request, "strategies": strategies}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/portfolio/equity-chart", response_class=HTMLResponse)
async def equity_chart_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get equity curve chart partial for HTMX."""
    try:
        service = PortfolioService(db)
        chart_data = service.get_equity_curve()
        return templates.TemplateResponse(
            "partials/equity_chart.html",
            {
                "request": request,
                "labels": chart_data.get("labels", []),
                "values": chart_data.get("values", [])
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/watchlist/data", response_class=HTMLResponse)
async def watchlist_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get watchlist data partial for HTMX."""
    try:
        service = MarketService(db)
        watchlist = service.get_watchlist()
        return templates.TemplateResponse(
            "partials/watchlist_data.html",
            {"request": request, "watchlist": watchlist}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/partials/sentiment/market", response_class=HTMLResponse)
async def sentiment_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get market sentiment partial for HTMX."""
    try:
        service = SentimentService(db)
        sentiment = service.get_market_sentiment()
        wsb_trending = service.get_wsb_trending()
        return templates.TemplateResponse(
            "partials/sentiment_market.html",
            {"request": request, "sentiment": sentiment, "wsb_trending": wsb_trending}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/api/v1/risk/gauges", response_class=HTMLResponse)
async def risk_exposure_gauge(request: Request, db: Session = Depends(get_db_session)):
    """Get exposure gauge partial for HTMX."""
    try:
        service = RiskService(db)
        metrics = service.get_current_metrics()
        exposure_pct = metrics.get("exposure_pct", 0)
        exposure_value = metrics.get("positions_value", 0)
        return templates.TemplateResponse(
            "partials/risk_gauges.html",
            {
                "request": request,
                "title": "Exposure",
                "value": exposure_pct,
                "max_value": metrics.get("max_exposure_pct", 100),
                "label": f"{exposure_pct:.1f}% / {metrics.get('max_exposure_pct', 100)}%",
                "unit": "%",
                "status_ok": metrics.get("exposure_ok", True),
                "status_text": f"${exposure_value:,.0f} invested"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/api/v1/risk/daily-pnl-gauge", response_class=HTMLResponse)
async def risk_daily_pnl_gauge(request: Request, db: Session = Depends(get_db_session)):
    """Get daily P&L gauge partial for HTMX."""
    try:
        service = RiskService(db)
        metrics = service.get_current_metrics()
        daily_pnl_pct = metrics.get("daily_pnl_pct", 0)
        limit = metrics.get("daily_loss_limit_pct", 5)

        # Only show loss if day is negative, otherwise show 0
        daily_loss_pct = abs(daily_pnl_pct) if daily_pnl_pct < 0 else 0

        # Get dollar P&L for context
        daily_pnl_dollar = metrics.get("daily_pnl", 0)

        return templates.TemplateResponse(
            "partials/risk_gauges.html",
            {
                "request": request,
                "title": "Daily Loss",
                "value": daily_loss_pct,
                "max_value": limit,
                "label": f"{daily_loss_pct:.2f}% / {limit}%",
                "unit": "%",
                "status_ok": metrics.get("daily_loss_ok", True),
                "status_text": f"${daily_pnl_dollar:+,.0f} today" if daily_pnl_pct >= 0 else "Limit reached" if not metrics.get("daily_loss_ok") else f"${daily_pnl_dollar:,.0f} loss"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


@router.get("/api/v1/risk/position-concentration", response_class=HTMLResponse)
async def risk_position_gauge(request: Request, db: Session = Depends(get_db_session)):
    """Get position concentration gauge partial for HTMX."""
    try:
        service = RiskService(db)
        metrics = service.get_current_metrics()
        max_pos_value = metrics.get("max_position_value", 0)
        max_pos_pct = metrics.get("max_position_pct", 0)
        max_pos_symbol = metrics.get("max_position_symbol") or "None"
        return templates.TemplateResponse(
            "partials/risk_gauges.html",
            {
                "request": request,
                "title": "Max Position",
                "value": max_pos_pct,
                "max_value": metrics.get("max_position_limit_pct", 20),
                "label": max_pos_symbol,
                "unit": "%",
                "status_ok": metrics.get("position_concentration_ok", True),
                "status_text": f"${max_pos_value:,.0f} ({max_pos_pct:.1f}%)"
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)}
        )


# Page routes for navigation
@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request):
    """Render portfolio page."""
    return templates.TemplateResponse("pages/portfolio.html", {"request": request})


@router.get("/positions", response_class=HTMLResponse)
async def positions_page(request: Request):
    """Render positions page."""
    return templates.TemplateResponse("pages/positions.html", {"request": request})


@router.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request):
    """Render trades page."""
    return templates.TemplateResponse("pages/trades.html", {"request": request})


@router.get("/signals", response_class=HTMLResponse)
async def signals_page(request: Request):
    """Render signals page."""
    return templates.TemplateResponse("pages/signals.html", {"request": request})


@router.get("/strategies", response_class=HTMLResponse)
async def strategies_page(request: Request):
    """Render strategies page."""
    return templates.TemplateResponse("pages/strategies.html", {"request": request})


@router.get("/risk", response_class=HTMLResponse)
async def risk_page(request: Request):
    """Render risk page."""
    return templates.TemplateResponse("pages/risk.html", {"request": request})


@router.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request):
    """Render watchlist page."""
    return templates.TemplateResponse("pages/watchlist.html", {"request": request})


@router.get("/grid", response_class=HTMLResponse)
async def grid_page(request: Request):
    """Render grid trading page."""
    return templates.TemplateResponse("pages/grid.html", {"request": request})
