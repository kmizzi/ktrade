"""
Structured logging setup using structlog for JSON-formatted logs.
Provides context-aware logging with automatic timestamping and structured data.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict
import structlog
from config.settings import settings


def setup_logging() -> structlog.BoundLogger:
    """
    Configure structured logging with JSON output.

    Returns:
        Configured structlog logger
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # File handler for persistent logs
    log_file = log_dir / f"ktrade_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, settings.log_level))

    # Get root logger and add file handler
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger()
    logger.info(
        "logging_initialized",
        log_level=settings.log_level,
        log_file=str(log_file),
        environment=settings.environment,
        bot_mode=settings.bot_mode
    )

    return logger


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LogContext:
    """
    Context manager for adding context to logs.

    Example:
        with LogContext(trade_id=123, symbol="AAPL"):
            logger.info("executing_trade")
    """

    def __init__(self, **kwargs: Any):
        self.context = kwargs

    def __enter__(self) -> None:
        structlog.contextvars.bind_contextvars(**self.context)

    def __exit__(self, *args: Any) -> None:
        structlog.contextvars.unbind_contextvars(*self.context.keys())


# Convenience functions for common log events
def log_trade_execution(
    logger: structlog.BoundLogger,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    order_id: str,
    strategy: str,
    **kwargs: Any
) -> None:
    """Log trade execution event"""
    logger.info(
        "trade_executed",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        order_id=order_id,
        strategy=strategy,
        total_value=quantity * price,
        **kwargs
    )


def log_signal_generated(
    logger: structlog.BoundLogger,
    symbol: str,
    signal_type: str,
    confidence: float,
    strategy: str,
    **kwargs: Any
) -> None:
    """Log signal generation event"""
    logger.info(
        "signal_generated",
        symbol=symbol,
        signal_type=signal_type,
        confidence=confidence,
        strategy=strategy,
        **kwargs
    )


def log_error(
    logger: structlog.BoundLogger,
    error_type: str,
    error_message: str,
    **kwargs: Any
) -> None:
    """Log error event"""
    logger.error(
        "error_occurred",
        error_type=error_type,
        error_message=error_message,
        **kwargs
    )


def log_portfolio_snapshot(
    logger: structlog.BoundLogger,
    total_value: float,
    cash: float,
    positions_value: float,
    daily_return_pct: float,
    **kwargs: Any
) -> None:
    """Log portfolio snapshot event"""
    logger.info(
        "portfolio_snapshot",
        total_value=total_value,
        cash=cash,
        positions_value=positions_value,
        daily_return_pct=daily_return_pct,
        **kwargs
    )
