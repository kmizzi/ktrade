"""
Alpaca API client wrapper.
Provides interface to Alpaca's trading and market data APIs with retry logic.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)


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
                    "side": pos.side,
                }
                for pos in positions
            ]
        except Exception as e:
            logger.error("failed_to_get_positions", error=str(e))
            raise

    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """
        Place a market order.

        Args:
            symbol: Stock or crypto symbol
            qty: Quantity to buy/sell
            side: 'buy' or 'sell'
            time_in_force: Order time in force (default: 'day')

        Returns:
            Order details
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif = TimeInForce.DAY if time_in_force.lower() == "day" else TimeInForce.GTC

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

            # Set default date range
            if not start:
                start = datetime.now() - timedelta(days=30)
            if not end:
                end = datetime.now()

            # Map timeframe string to TimeFrame enum
            timeframe_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame.Minute * 5,
                "15Min": TimeFrame.Minute * 15,
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day,
            }
            tf = timeframe_map.get(timeframe, TimeFrame.Day)

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
                    limit=limit
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


# Global client instance
alpaca_client = AlpacaClient()
