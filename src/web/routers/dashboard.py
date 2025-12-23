"""
Main dashboard routes.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

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
async def trades_partial(request: Request, db: Session = Depends(get_db_session)):
    """Get recent trades partial for HTMX."""
    try:
        service = TradeService(db)
        trades = service.get_recent_trades(limit=5)
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
        return templates.TemplateResponse(
            "partials/risk_gauges.html",
            {
                "request": request,
                "title": "Exposure",
                "value": metrics.get("exposure_pct", 0),
                "max_value": metrics.get("max_exposure_pct", 100),
                "label": f"{metrics.get('exposure_pct', 0):.1f}% / {metrics.get('max_exposure_pct', 100)}%",
                "unit": "%",
                "status_ok": metrics.get("exposure_ok", True),
                "status_text": "Within limits" if metrics.get("exposure_ok") else "Over limit"
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
        daily_loss_pct = abs(metrics.get("daily_pnl_pct", 0))
        limit = metrics.get("daily_loss_limit_pct", 5)
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
                "status_text": "OK" if metrics.get("daily_loss_ok") else "Limit reached"
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
        return templates.TemplateResponse(
            "partials/risk_gauges.html",
            {
                "request": request,
                "title": "Max Position",
                "value": metrics.get("max_position_pct", 0),
                "max_value": metrics.get("max_position_limit_pct", 20),
                "label": metrics.get("max_position_symbol") or "None",
                "unit": "%",
                "status_ok": metrics.get("position_concentration_ok", True),
                "status_text": f"{metrics.get('max_position_pct', 0):.1f}%"
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
