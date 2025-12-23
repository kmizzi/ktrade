"""
Alpaca API client wrapper.
Provides interface to Alpaca's trading and market data APIs with retry logic.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderClass
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed
from alpaca.common.exceptions import APIError
import structlog
from functools import wraps

from config.settings import settings

logger = structlog.get_logger(__name__)


class RateLimitException(Exception):
    """Raised when Alpaca API rate limit is hit"""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds.")


def handle_rate_limit(func):
    """Decorator to detect rate limit errors and raise RateLimitException"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            # Check for rate limit (HTTP 429)
            error_str = str(e).lower()
            if '429' in str(e) or 'rate limit' in error_str or 'too many requests' in error_str:
                # Try to extract retry-after from error, default to 60 seconds
                retry_after = 60
                logger.warning("rate_limit_hit", function=func.__name__, retry_after=retry_after)
                raise RateLimitException(retry_after=retry_after)
            raise
    return wrapper


class AlpacaClient:
    """
    Wrapper around Alpaca API with retry logic and error handling.
    Handles both trading operations and market data retrieval.
    """

    def __init__(self):
        """Initialize Alpaca clients"""
        self.trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.is_paper_trading
        )

        self.stock_data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key
        )

        self.crypto_data_client = CryptoHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key
        )

        logger.info(
            "alpaca_client_initialized",
            paper_trading=settings.is_paper_trading,
            base_url=settings.alpaca_base_url
        )

    @handle_rate_limit
    def get_account(self) -> Dict[str, Any]:
        """
        Get account information.

        Returns:
            Dict with account details including cash, portfolio_value, etc.
        """
        try:
            account = self.trading_client.get_account()
            return {
                "cash": float(account.cash),
                "portfolio_value": float(account.portfolio_value),
                "buying_power": float(account.buying_power),
                "equity": float(account.equity),
                "last_equity": float(account.last_equity),
                "pattern_day_trader": account.pattern_day_trader,
                "daytrade_count": account.daytrade_count,
                "account_blocked": account.account_blocked,
                "trading_blocked": account.trading_blocked,
            }
        except Exception as e:
            logger.error("failed_to_get_account", error=str(e))
            raise

    @handle_rate_limit
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all open positions.

        Returns:
            List of positions with details
        """
        try:
            positions = self.trading_client.get_all_positions()
            return [
                {
                    "symbol": pos.symbol,
                    "qty": float(pos.qty),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "current_price": float(pos.current_price),
                    "market_value": float(pos.market_value),
                    "cost_basis": float(pos.cost_basis),
                    "unrealized_pl": float(pos.unrealized_pl),
                    "unrealized_plpc": float(pos.unrealized_plpc),
                    "unrealized_intraday_pl": float(pos.unrealized_intraday_pl) if pos.unrealized_intraday_pl else 0,
                    "unrealized_intraday_plpc": float(pos.unrealized_intraday_plpc) if pos.unrealized_intraday_plpc else 0,
                    "change_today": float(pos.change_today) if pos.change_today else 0,
                    "lastday_price": float(pos.lastday_price) if pos.lastday_price else 0,
                    "side": pos.side,
                }
                for pos in positions
            ]
        except Exception as e:
            logger.error("failed_to_get_positions", error=str(e))
            raise

    @handle_rate_limit
    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        time_in_force: str = "auto"
    ) -> Dict[str, Any]:
        """
        Place a market order.

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to buy/sell
            side: 'buy' or 'sell'
            time_in_force: Order time in force (default: 'auto' - GTC for crypto, DAY for stocks)

        Returns:
            Order details
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            # Crypto symbols contain "/" and require GTC
            is_crypto = "/" in symbol
            if time_in_force.lower() == "auto":
                tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY
            else:
                tif = TimeInForce.GTC if time_in_force.lower() == "gtc" else TimeInForce.DAY

            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif
            )

            order = self.trading_client.submit_order(request)

            logger.info(
                "market_order_placed",
                symbol=symbol,
                side=side,
                qty=qty,
                order_id=order.id
            )

            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "status": order.status.value,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at,
            }

        except Exception as e:
            logger.error(
                "failed_to_place_market_order",
                symbol=symbol,
                side=side,
                qty=qty,
                error=str(e)
            )
            raise

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        stop_loss_price: float,
        take_profit_price: float,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Place a bracket order (entry + stop loss + take profit).

        A bracket order is a chain of three orders:
        1. Entry order (market)
        2. Stop loss order (triggered if price falls)
        3. Take profit order (triggered if price rises)

        Only one of stop loss or take profit will execute (OCO).

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to buy/sell
            side: 'buy' or 'sell'
            stop_loss_price: Price to trigger stop loss
            take_profit_price: Price to trigger take profit
            time_in_force: Order time in force (default: 'gtc' for bracket)

        Returns:
            Order details including leg order IDs
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            # Fractional orders must be DAY orders (Alpaca requirement)
            is_fractional = qty != int(qty)
            if time_in_force == "auto" or time_in_force == "gtc":
                tif = TimeInForce.DAY if is_fractional else TimeInForce.GTC
            else:
                tif = TimeInForce.DAY

            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=tif,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=take_profit_price),
                stop_loss=StopLossRequest(stop_price=stop_loss_price)
            )

            order = self.trading_client.submit_order(request)

            logger.info(
                "bracket_order_placed",
                symbol=symbol,
                side=side,
                qty=qty,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                order_id=order.id
            )

            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "order_class": order.order_class.value if order.order_class else None,
                "status": order.status.value,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "legs": [{"id": leg.id, "type": leg.type.value} for leg in order.legs] if order.legs else [],
                "submitted_at": order.submitted_at,
            }

        except Exception as e:
            logger.error(
                "failed_to_place_bracket_order",
                symbol=symbol,
                side=side,
                qty=qty,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                error=str(e)
            )
            raise

    @handle_rate_limit
    def place_stop_order(
        self,
        symbol: str,
        qty: float,
        stop_price: float,
        side: str = "sell",
        time_in_force: str = "auto"
    ) -> Dict[str, Any]:
        """
        Place a stop order (for stop-loss on existing positions).

        This creates a sell stop order that triggers when price falls to stop_price.

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to sell
            stop_price: Price at which to trigger the stop
            side: 'sell' for stop-loss (default)
            time_in_force: Order time in force (default: 'auto' - DAY for fractional, GTC for whole)

        Returns:
            Order details
        """
        try:
            order_side = OrderSide.SELL if side.lower() == "sell" else OrderSide.BUY

            # Fractional orders must be DAY orders (Alpaca requirement)
            is_fractional = qty != int(qty)
            if time_in_force == "auto":
                tif = TimeInForce.DAY if is_fractional else TimeInForce.GTC
            else:
                tif = TimeInForce.GTC if time_in_force.lower() == "gtc" else TimeInForce.DAY

            request = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                stop_price=stop_price,
                time_in_force=tif
            )

            order = self.trading_client.submit_order(request)

            logger.info(
                "stop_order_placed",
                symbol=symbol,
                side=side,
                qty=qty,
                stop_price=stop_price,
                order_id=order.id
            )

            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "status": order.status.value,
                "stop_price": stop_price,
                "submitted_at": order.submitted_at,
            }

        except Exception as e:
            logger.error(
                "failed_to_place_stop_order",
                symbol=symbol,
                stop_price=stop_price,
                error=str(e)
            )
            raise

    @handle_rate_limit
    def place_trailing_stop_order(
        self,
        symbol: str,
        qty: float,
        trail_percent: float,
        side: str = "sell",
        time_in_force: str = "auto"
    ) -> Dict[str, Any]:
        """
        Place a trailing stop order.

        The stop price follows the market price by the trail_percent.
        If the stock rises, the stop price rises. If it falls, the stop triggers.

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to sell
            trail_percent: Percentage to trail (e.g., 5.0 for 5%)
            side: 'sell' for stop-loss (default)
            time_in_force: Order time in force (default: 'auto' - DAY for fractional, GTC for whole)

        Returns:
            Order details
        """
        try:
            order_side = OrderSide.SELL if side.lower() == "sell" else OrderSide.BUY

            # Fractional orders must be DAY orders (Alpaca requirement)
            is_fractional = qty != int(qty)
            if time_in_force == "auto":
                tif = TimeInForce.DAY if is_fractional else TimeInForce.GTC
            else:
                tif = TimeInForce.GTC if time_in_force.lower() == "gtc" else TimeInForce.DAY

            request = TrailingStopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                trail_percent=trail_percent,
                time_in_force=tif
            )

            order = self.trading_client.submit_order(request)

            logger.info(
                "trailing_stop_order_placed",
                symbol=symbol,
                side=side,
                qty=qty,
                trail_percent=trail_percent,
                order_id=order.id
            )

            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "status": order.status.value,
                "trail_percent": trail_percent,
                "submitted_at": order.submitted_at,
            }

        except Exception as e:
            logger.error(
                "failed_to_place_trailing_stop_order",
                symbol=symbol,
                trail_percent=trail_percent,
                error=str(e)
            )
            raise

    @handle_rate_limit
    def place_limit_order(
        self,
        symbol: str,
        qty: float,
        limit_price: float,
        side: str,
        time_in_force: str = "gtc",
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place a limit order at a specified price.

        Used by grid trading strategy to place orders at predetermined levels.

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to buy/sell
            limit_price: Price at which to execute
            side: 'buy' or 'sell'
            time_in_force: Order time in force (default: 'gtc')
            client_order_id: Optional client-specified order ID for tracking

        Returns:
            Order details
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.GTC if time_in_force.lower() == "gtc" else TimeInForce.DAY

            request = LimitOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                limit_price=limit_price,
                time_in_force=tif,
                client_order_id=client_order_id
            )

            order = self.trading_client.submit_order(request)

            logger.info(
                "limit_order_placed",
                symbol=symbol,
                side=side,
                qty=qty,
                limit_price=limit_price,
                order_id=order.id,
                client_order_id=client_order_id
            )

            return {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "limit_price": limit_price,
                "status": order.status.value,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at,
            }

        except Exception as e:
            logger.error(
                "failed_to_place_limit_order",
                symbol=symbol,
                side=side,
                qty=qty,
                limit_price=limit_price,
                error=str(e)
            )
            raise

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancelled successfully
        """
        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info("order_cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.error("failed_to_cancel_order", order_id=order_id, error=str(e))
            return False

    @handle_rate_limit
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            List of open orders
        """
        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None
            )
            orders = self.trading_client.get_orders(request)

            return [
                {
                    "id": order.id,
                    "symbol": order.symbol,
                    "qty": float(order.qty) if order.qty else 0,
                    "side": order.side.value,
                    "type": order.type.value,
                    "status": order.status.value,
                    "stop_price": float(order.stop_price) if order.stop_price else None,
                    "limit_price": float(order.limit_price) if order.limit_price else None,
                    "submitted_at": order.submitted_at,
                }
                for order in orders
            ]
        except Exception as e:
            logger.error("failed_to_get_open_orders", symbol=symbol, error=str(e))
            return []

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Get order by ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order details
        """
        try:
            order = self.trading_client.get_order_by_id(order_id)
            return {
                "id": order.id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "type": order.type.value,
                "status": order.status.value,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at,
                "filled_at": order.filled_at,
            }
        except Exception as e:
            logger.error("failed_to_get_order", order_id=order_id, error=str(e))
            raise

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Close an entire position.

        Args:
            symbol: Symbol to close

        Returns:
            Order details for closing order
        """
        try:
            order = self.trading_client.close_position(symbol)
            logger.info("position_closed", symbol=symbol, order_id=order.id)

            return {
                "id": order.id,
                "symbol": order.symbol,
                "qty": float(order.qty) if order.qty else 0,
                "side": order.side.value,
                "status": order.status.value,
            }
        except Exception as e:
            logger.error("failed_to_close_position", symbol=symbol, error=str(e))
            raise

    @handle_rate_limit
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical bar data for a symbol.

        Args:
            symbol: Stock or crypto symbol
            timeframe: Bar timeframe (e.g., '1Min', '1Hour', '1Day')
            start: Start datetime
            end: End datetime
            limit: Maximum number of bars

        Returns:
            List of bar data
        """
        try:
            # Determine if stock or crypto
            is_crypto = "/" in symbol

            # Set default date range (need ~60+ trading days for indicators)
            if not start:
                start = datetime.now() - timedelta(days=120)
            if not end:
                end = datetime.now()

            # Map timeframe string to TimeFrame enum
            if timeframe == "1Min":
                tf = TimeFrame.Minute
            elif timeframe == "5Min":
                tf = TimeFrame.Minute
                # Note: For 5Min need to aggregate client-side or use different approach
            elif timeframe == "15Min":
                tf = TimeFrame.Minute
                # Note: For 15Min need to aggregate client-side or use different approach
            elif timeframe == "1Hour":
                tf = TimeFrame.Hour
            elif timeframe == "1Day":
                tf = TimeFrame.Day
            else:
                tf = TimeFrame.Day

            if is_crypto:
                request = CryptoBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf,
                    start=start,
                    end=end,
                    limit=limit
                )
                bars = self.crypto_data_client.get_crypto_bars(request)
            else:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf,
                    start=start,
                    end=end,
                    limit=limit,
                    feed=DataFeed.IEX  # Use IEX for free tier compatibility
                )
                bars = self.stock_data_client.get_stock_bars(request)

            # Extract data
            if symbol in bars.data:
                return [
                    {
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume),
                    }
                    for bar in bars.data[symbol]
                ]
            return []

        except Exception as e:
            logger.error(
                "failed_to_get_bars",
                symbol=symbol,
                timeframe=timeframe,
                error=str(e)
            )
            raise

    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest quote for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Latest quote data or None
        """
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self.stock_data_client.get_stock_latest_quote(request)

            if symbol in quotes:
                quote = quotes[symbol]
                return {
                    "symbol": symbol,
                    "bid_price": float(quote.bid_price),
                    "ask_price": float(quote.ask_price),
                    "bid_size": float(quote.bid_size),
                    "ask_size": float(quote.ask_size),
                    "timestamp": quote.timestamp,
                }
            return None

        except Exception as e:
            logger.error("failed_to_get_latest_quote", symbol=symbol, error=str(e))
            return None

    def is_market_open(self) -> bool:
        """
        Check if the market is currently open.

        Returns:
            True if market is open, False otherwise
        """
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error("failed_to_get_market_clock", error=str(e))
            # Default to False if we can't check
            return False

    def get_clock(self) -> Dict[str, Any]:
        """
        Get market clock information.

        Returns:
            Dict with market clock details
        """
        try:
            clock = self.trading_client.get_clock()
            return {
                "is_open": clock.is_open,
                "next_open": clock.next_open,
                "next_close": clock.next_close,
                "timestamp": clock.timestamp,
            }
        except Exception as e:
            logger.error("failed_to_get_clock", error=str(e))
            return {"is_open": False}


# Global client instance
alpaca_client = AlpacaClient()
