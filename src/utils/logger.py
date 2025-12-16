"""
Structured logging setup with dual log files:
- ktrade.log: Human-readable, plain text, key events only
- ktrade_debug.log: JSON format, all events, full technical detail
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
import structlog
from config.settings import settings


# Events that are important for human-readable log
HUMAN_LOG_EVENTS = {
    # Lifecycle
    'trading_bot_starting',
    'bot_running_press_ctrl_c_to_stop',
    'scheduler_started',
    'alpaca_connected',
    'starting_perpetual_strategy_loop',
    'bot_shutdown_requested',
    'bot_stopped',

    # Perpetual loop
    'perpetual_cycle_starting',
    'perpetual_cycle_completed',
    'market_closed_waiting',
    'rate_limit_backoff',
    'rate_limit_hit',

    # Trailing stop management
    'trailing_stop_tightened',
    'trailing_stop_tightened_on_sell_signal',
    'processing_sell_signal',

    # Trading
    'trade_executed',
    'entry_order_placed',
    'entry_order_filled',
    'position_opened',
    'position_closed',
    'closing_position_risk',
    'closing_position_strategy',

    # Signals
    'signal_generated',
    'executing_signal',
    'signal_executed_successfully',

    # Portfolio
    'portfolio_state',
    'portfolio_snapshot',
    'positions_synced',

    # Risk management
    'daily_loss_limit_exceeded',
    'trade_rejected_by_risk_manager',
    'daily_tracking_reset',

    # Discovery
    'dynamic_watchlist_generated',
    'top_gainers_found',
    'high_volume_stocks_found',

    # Errors and warnings (always include)
    'error_occurred',
    'error',
}


class HumanReadableFormatter(logging.Formatter):
    """Formats log messages for human readability"""

    def format(self, record: logging.LogRecord) -> str:
        # Get timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname.ljust(5)

        # Try to extract structured data from the message
        msg = record.getMessage()

        # Handle structlog JSON messages
        if msg.startswith('{') and msg.endswith('}'):
            try:
                import json
                data = json.loads(msg)
                return self._format_structured(timestamp, level, data)
            except json.JSONDecodeError:
                pass

        return f"{timestamp} | {level} | {msg}"

    def _format_structured(self, timestamp: str, level: str, data: Dict) -> str:
        """Format structured log data for human readability"""
        event = data.get('event', 'unknown')

        # Format based on event type
        if event == 'trading_bot_starting':
            mode = data.get('bot_mode', 'unknown')
            return f"{timestamp} | {level} | Bot starting in {mode} mode"

        elif event == 'alpaca_connected':
            value = data.get('portfolio_value', 0)
            cash = data.get('cash', 0)
            return f"{timestamp} | {level} | Connected to Alpaca | Portfolio: ${value:,.2f} | Cash: ${cash:,.2f}"

        elif event == 'portfolio_state':
            value = data.get('total_value', 0)
            cash = data.get('cash', 0)
            positions = data.get('position_count', 0)
            pos_value = data.get('positions_value', 0)
            return f"{timestamp} | {level} | Portfolio: ${value:,.2f} | Cash: ${cash:,.2f} | Positions: {positions} (${pos_value:,.2f})"

        elif event == 'signal_generated':
            symbol = data.get('symbol', '?')
            sig_type = data.get('signal_type', '?').upper()
            confidence = data.get('confidence', 0)
            strategy = data.get('strategy', '?')
            return f"{timestamp} | {level} | Signal: {sig_type} {symbol} | Confidence: {confidence:.0%} | Strategy: {strategy}"

        elif event == 'executing_signal':
            symbol = data.get('symbol', '?')
            confidence = data.get('confidence', 0)
            return f"{timestamp} | {level} | Executing signal for {symbol} (confidence: {confidence:.0%})"

        elif event == 'entry_order_placed':
            symbol = data.get('symbol', '?')
            qty = data.get('quantity', 0)
            price = data.get('price', 0)
            return f"{timestamp} | {level} | Order placed: BUY {qty} {symbol} @ ${price:.2f}"

        elif event == 'entry_order_filled':
            symbol = data.get('symbol', '?')
            qty = data.get('filled_qty', 0)
            price = data.get('filled_price', 0)
            total = qty * price if qty and price else 0
            return f"{timestamp} | {level} | Order filled: BUY {qty} {symbol} @ ${price:.2f} (${total:,.2f})"

        elif event == 'position_opened':
            symbol = data.get('symbol', '?')
            qty = data.get('quantity', 0)
            price = data.get('entry_price', 0)
            return f"{timestamp} | {level} | Position opened: {symbol} | {qty} shares @ ${price:.2f}"

        elif event == 'position_closed':
            symbol = data.get('symbol', '?')
            reason = data.get('reason', 'unknown')
            return f"{timestamp} | {level} | Position closed: {symbol} | Reason: {reason}"

        elif event in ('closing_position_risk', 'closing_position_strategy'):
            symbol = data.get('symbol', '?')
            reason = data.get('reason', 'unknown')
            return f"{timestamp} | {level} | Closing position: {symbol} | {reason}"

        elif event == 'trade_rejected_by_risk_manager':
            symbol = data.get('symbol', '?')
            reason = data.get('reason', 'unknown')
            return f"{timestamp} | {level} | Trade rejected: {symbol} | {reason}"

        elif event == 'daily_loss_limit_exceeded':
            pct = data.get('daily_return_pct', 0)
            return f"{timestamp} | {level} | DAILY LOSS LIMIT EXCEEDED ({pct:.2f}%) - Trading halted"

        elif event == 'positions_synced':
            alpaca = data.get('alpaca_count', 0)
            db = data.get('db_count', 0)
            return f"{timestamp} | {level} | Positions synced: {alpaca} on Alpaca, {db} in DB"

        elif event == 'top_gainers_found':
            count = data.get('count', 0)
            symbols = data.get('symbols', [])[:5]
            return f"{timestamp} | {level} | Top gainers: {', '.join(symbols)} ({count} total)"

        elif event == 'high_volume_stocks_found':
            count = data.get('count', 0)
            symbols = data.get('symbols', [])[:5]
            return f"{timestamp} | {level} | High volume: {', '.join(symbols)} ({count} total)"

        elif event == 'dynamic_watchlist_generated':
            count = data.get('count', 0)
            symbols = data.get('symbols', [])[:10]
            return f"{timestamp} | {level} | Watchlist: {', '.join(symbols)} ({count} total)"

        elif event == 'scheduler_started':
            return f"{timestamp} | {level} | Scheduler started"

        elif event == 'bot_running_press_ctrl_c_to_stop':
            return f"{timestamp} | {level} | Bot running (Ctrl+C to stop)"

        elif event == 'starting_perpetual_strategy_loop':
            return f"{timestamp} | {level} | Starting perpetual strategy loop (reactive rate limiting)"

        elif event == 'perpetual_cycle_starting':
            cycle = data.get('cycle', '?')
            return f"{timestamp} | {level} | Strategy cycle #{cycle} starting"

        elif event == 'perpetual_cycle_completed':
            cycle = data.get('cycle', '?')
            return f"{timestamp} | {level} | Strategy cycle #{cycle} completed"

        elif event == 'market_closed_waiting':
            next_open = data.get('next_open', 'unknown')
            return f"{timestamp} | {level} | Market closed, waiting... Next open: {next_open}"

        elif event == 'rate_limit_backoff':
            retry_after = data.get('retry_after', 60)
            cycle = data.get('cycle', '?')
            return f"{timestamp} | {level} | Rate limit hit at cycle #{cycle}, backing off for {retry_after}s"

        elif event == 'rate_limit_hit':
            func = data.get('function', 'unknown')
            retry_after = data.get('retry_after', 60)
            return f"{timestamp} | {level} | Rate limit on {func}, retry in {retry_after}s"

        elif event == 'bot_shutdown_requested':
            return f"{timestamp} | {level} | Shutdown requested"

        elif event == 'bot_stopped':
            return f"{timestamp} | {level} | Bot stopped"

        elif event == 'trailing_stop_tightened' or event == 'trailing_stop_tightened_on_sell_signal':
            symbol = data.get('symbol', '?')
            old_pct = data.get('old_trail_pct', '?')
            new_pct = data.get('new_trail_pct', '?')
            pnl_pct = data.get('pnl_pct', 0)
            reason = data.get('reason', '')
            return f"{timestamp} | {level} | TRAILING STOP TIGHTENED: {symbol} | {old_pct}% → {new_pct}% | P&L: {pnl_pct:.1f}% | {reason}"

        elif event == 'processing_sell_signal':
            symbol = data.get('symbol', '?')
            confidence = data.get('confidence', 0)
            pnl_pct = data.get('pnl_pct', 0)
            reason = data.get('reason', '')
            return f"{timestamp} | {level} | SELL signal for {symbol} | Confidence: {confidence:.0%} | P&L: {pnl_pct:.1f}% | {reason}"

        elif 'error' in event.lower() or data.get('level') == 'error':
            error_msg = data.get('error', data.get('error_message', str(data)))
            return f"{timestamp} | ERROR | {event}: {error_msg}"

        # Default: show event name and key data
        important_keys = ['symbol', 'reason', 'message', 'count']
        details = ' | '.join(f"{k}: {data[k]}" for k in important_keys if k in data)
        if details:
            return f"{timestamp} | {level} | {event} | {details}"
        return f"{timestamp} | {level} | {event}"


class HumanLogFilter(logging.Filter):
    """Filter to only allow important events in human-readable log"""

    def filter(self, record: logging.LogRecord) -> bool:
        # Always include warnings and errors
        if record.levelno >= logging.WARNING:
            return True

        # Check if message contains an important event
        msg = record.getMessage()
        if msg.startswith('{'):
            try:
                import json
                data = json.loads(msg)
                event = data.get('event', '')
                return event in HUMAN_LOG_EVENTS
            except json.JSONDecodeError:
                pass

        # Include non-JSON messages (like APScheduler output)
        return True


def setup_logging() -> structlog.BoundLogger:
    """
    Configure dual logging: human-readable and debug JSON logs.

    Returns:
        Configured structlog logger
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(logging.DEBUG)

    # === Human-readable log ===
    human_log_file = log_dir / "ktrade.log"
    human_handler = RotatingFileHandler(
        human_log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    human_handler.setLevel(logging.INFO)
    human_handler.setFormatter(HumanReadableFormatter())
    human_handler.addFilter(HumanLogFilter())
    root_logger.addHandler(human_handler)

    # === Debug JSON log ===
    debug_log_file = log_dir / "ktrade_debug.log"
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter('%(message)s'))
    root_logger.addHandler(debug_handler)

    # === Console output (minimal) ===
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)

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
        human_log=str(human_log_file),
        debug_log=str(debug_log_file),
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
