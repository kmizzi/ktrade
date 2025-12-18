"""
Main backtesting engine.
Runs strategies against historical data and tracks performance.
"""

from typing import List, Dict, Any, Optional, Type
from datetime import datetime, timedelta
import pandas as pd
import structlog

from src.backtest.data import HistoricalDataFetcher
from src.backtest.portfolio import SimulatedPortfolio
from src.backtest.metrics import calculate_metrics, PerformanceMetrics, generate_report
from src.strategies.base import BaseStrategy
from src.data.indicators import calculate_all_indicators, get_latest_indicators
from config.settings import settings

logger = structlog.get_logger(__name__)


class Backtester:
    """
    Main backtesting engine.

    Runs a trading strategy against historical data and calculates
    performance metrics.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_cash: float = 100000.0,
        commission: float = 0.0,
        trailing_stop_pct: float = 7.0,
        use_trailing_stops: bool = True
    ):
        """
        Initialize backtester.

        Args:
            strategy: Trading strategy to test
            initial_cash: Starting cash amount
            commission: Commission per trade
            trailing_stop_pct: Trailing stop percentage
            use_trailing_stops: Whether to use trailing stops
        """
        self.strategy = strategy
        self.initial_cash = initial_cash
        self.commission = commission
        self.trailing_stop_pct = trailing_stop_pct
        self.use_trailing_stops = use_trailing_stops

        self.data_fetcher = HistoricalDataFetcher()
        self.portfolio = SimulatedPortfolio(
            initial_cash=initial_cash,
            commission_per_trade=commission,
            max_position_pct=settings.max_position_size_pct
        )

        self._historical_data: Dict[str, pd.DataFrame] = {}
        self._results: Optional[PerformanceMetrics] = None

    def load_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Day"
    ):
        """
        Load historical data for backtesting.

        Args:
            symbols: List of symbols to test
            start_date: Start date
            end_date: End date
            timeframe: Bar timeframe
        """
        logger.info(
            "loading_backtest_data",
            symbols=symbols,
            start=start_date.isoformat(),
            end=end_date.isoformat()
        )

        self._historical_data = self.data_fetcher.get_multiple_symbols(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframe=timeframe
        )

        # Add indicators to each dataset
        for symbol, df in self._historical_data.items():
            if len(df) >= 50:
                # Convert to format expected by calculate_all_indicators
                bars = df.to_dict('records')
                df_with_indicators = calculate_all_indicators(bars)
                self._historical_data[symbol] = df_with_indicators

        logger.info(
            "backtest_data_loaded",
            symbols_loaded=len(self._historical_data),
            total_bars=sum(len(df) for df in self._historical_data.values())
        )

    def run(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        progress_callback: Optional[callable] = None
    ) -> PerformanceMetrics:
        """
        Run the backtest.

        Args:
            symbols: List of symbols to test
            start_date: Start date for backtest
            end_date: End date for backtest
            progress_callback: Optional callback for progress updates

        Returns:
            PerformanceMetrics with results
        """
        logger.info(
            "starting_backtest",
            strategy=self.strategy.name,
            symbols=symbols,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            initial_cash=self.initial_cash
        )

        # Load data if not already loaded
        if not self._historical_data:
            self.load_data(symbols, start_date, end_date)

        # Get all unique dates across all symbols
        all_dates = set()
        for df in self._historical_data.values():
            if 'timestamp' in df.columns:
                all_dates.update(df['timestamp'].dt.date.tolist())

        all_dates = sorted(all_dates)

        if not all_dates:
            logger.error("no_dates_to_backtest")
            return calculate_metrics(self.portfolio)

        logger.info("backtest_dates", total_days=len(all_dates))

        # Run simulation day by day
        for i, current_date in enumerate(all_dates):
            self._process_day(current_date, symbols)

            if progress_callback and i % 10 == 0:
                progress_callback(i, len(all_dates))

        # Close any remaining positions at the end
        self._close_all_positions(all_dates[-1])

        # Calculate metrics
        self._results = calculate_metrics(self.portfolio)

        logger.info(
            "backtest_complete",
            total_return=f"{self._results.total_return_pct:.2f}%",
            sharpe_ratio=f"{self._results.sharpe_ratio:.2f}",
            total_trades=self._results.total_trades,
            win_rate=f"{self._results.win_rate_pct:.1f}%"
        )

        return self._results

    def _process_day(self, date, symbols: List[str]):
        """Process a single day of the backtest."""
        current_prices = {}
        bars_for_signals = {}

        # Get data for this date
        for symbol in symbols:
            if symbol not in self._historical_data:
                continue

            df = self._historical_data[symbol]

            if 'timestamp' in df.columns:
                # Get all data up to and including this date
                mask = df['timestamp'].dt.date <= date
                historical = df[mask]

                if len(historical) >= 20:  # Need enough data for indicators
                    current_bar = historical.iloc[-1]
                    current_prices[symbol] = current_bar['close']
                    bars_for_signals[symbol] = historical

        if not current_prices:
            return

        # Create datetime for this date
        dt = datetime.combine(date, datetime.min.time())

        # Check stop losses and take profits for existing positions
        for symbol in list(self.portfolio.positions.keys()):
            if symbol in current_prices:
                price = current_prices[symbol]

                # Update trailing stop
                if self.use_trailing_stops:
                    self.portfolio.update_trailing_stop(
                        symbol, price, self.trailing_stop_pct
                    )

                # Check stop loss
                self.portfolio.check_stop_loss(symbol, price, dt)

        # Generate signals
        owned_symbols = self.portfolio.get_owned_symbols()

        for symbol, df in bars_for_signals.items():
            if len(df) < 50:
                continue

            price = current_prices.get(symbol)
            if not price:
                continue

            indicators = get_latest_indicators(df)

            # Check buy signals (only for symbols we don't own)
            if symbol not in owned_symbols and self._check_buy_signal(symbol, indicators, price):
                quantity = self.portfolio.calculate_position_size(
                    symbol, price, current_prices
                )

                if quantity > 0:
                    stop_loss = price * (1 - self.trailing_stop_pct / 100)
                    self.portfolio.buy(
                        symbol=symbol,
                        quantity=quantity,
                        price=price,
                        timestamp=dt,
                        stop_loss=stop_loss,
                        reason=f"Buy signal: RSI={indicators.get('rsi', 0):.1f}"
                    )

            # Check sell signals (only for symbols we own)
            elif symbol in owned_symbols and self._check_sell_signal(symbol, indicators, price):
                self.portfolio.sell(
                    symbol=symbol,
                    quantity=None,  # Sell all
                    price=price,
                    timestamp=dt,
                    reason=f"Sell signal: RSI={indicators.get('rsi', 0):.1f}"
                )

        # Take daily snapshot
        self.portfolio.take_snapshot(dt, current_prices)

    def _check_buy_signal(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        price: float
    ) -> bool:
        """
        Check if buy conditions are met.

        Uses the same logic as SimpleMomentumStrategy.
        """
        rsi = indicators.get('rsi')
        sma_20 = indicators.get('sma_20')

        if rsi is None or sma_20 is None:
            return False

        # Buy conditions:
        # - Price above 20-day SMA
        # - RSI between 40 and 70
        price_above_sma = price > sma_20
        rsi_in_range = 40 <= rsi <= 70

        return price_above_sma and rsi_in_range

    def _check_sell_signal(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        price: float
    ) -> bool:
        """
        Check if sell conditions are met.

        Uses the same logic as SimpleMomentumStrategy.
        """
        rsi = indicators.get('rsi')
        sma_20 = indicators.get('sma_20')

        if rsi is None or sma_20 is None:
            return False

        # Sell conditions:
        # - RSI > 75 (overbought)
        # - Price below 20-day SMA
        rsi_overbought = rsi > 75
        price_below_sma = price < sma_20

        return rsi_overbought or price_below_sma

    def _close_all_positions(self, final_date):
        """Close all remaining positions at end of backtest."""
        dt = datetime.combine(final_date, datetime.min.time())

        for symbol in list(self.portfolio.positions.keys()):
            if symbol in self._historical_data:
                df = self._historical_data[symbol]
                if not df.empty:
                    final_price = df.iloc[-1]['close']
                    self.portfolio.sell(
                        symbol=symbol,
                        quantity=None,
                        price=final_price,
                        timestamp=dt,
                        reason="End of backtest"
                    )

    def get_results(self) -> Optional[PerformanceMetrics]:
        """Get backtest results."""
        return self._results

    def get_report(self) -> str:
        """Generate a full backtest report."""
        if not self._results:
            return "No backtest results available. Run backtest first."

        return generate_report(
            self._results,
            self.portfolio,
            self.strategy.name
        )

    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        if not self.portfolio.snapshots:
            return pd.DataFrame()

        data = [
            {
                'date': s.timestamp,
                'total_value': s.total_value,
                'cash': s.cash,
                'positions_value': s.positions_value,
                'daily_return_pct': s.daily_return_pct
            }
            for s in self.portfolio.snapshots
        ]
        return pd.DataFrame(data)

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        if not self.portfolio.trades:
            return pd.DataFrame()

        data = [
            {
                'date': t.timestamp,
                'symbol': t.symbol,
                'side': t.side,
                'quantity': t.quantity,
                'price': t.price,
                'value': t.total_value,
                'reason': t.reason
            }
            for t in self.portfolio.trades
        ]
        return pd.DataFrame(data)

    def reset(self):
        """Reset backtester for a new run."""
        self.portfolio.reset()
        self._historical_data = {}
        self._results = None
