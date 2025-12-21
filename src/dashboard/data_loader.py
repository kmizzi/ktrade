"""
Data loader for the KTrade dashboard.
Fetches data from database, Alpaca API, and backtest files.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import pytz

# Project imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings

# Try to import database and API modules
try:
    from src.db.database import get_db, SessionLocal
    from src.db.models import Position, Trade
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

try:
    from src.api.alpaca_client import alpaca_client
    ALPACA_AVAILABLE = True
except Exception:
    ALPACA_AVAILABLE = False

try:
    from src.data.sentiment_providers import sentiment_aggregator, quiver_provider, stocktwits_provider
    SENTIMENT_AVAILABLE = True
except Exception:
    SENTIMENT_AVAILABLE = False


def is_market_open() -> bool:
    """Check if market is currently open."""
    if not ALPACA_AVAILABLE:
        return False

    try:
        clock = alpaca_client.get_clock()
        return clock.get('is_open', False)
    except Exception:
        return False


def get_portfolio_summary() -> Optional[Dict[str, Any]]:
    """Get portfolio summary from Alpaca."""
    if not ALPACA_AVAILABLE:
        # Return mock data or data from backtest
        return _get_mock_portfolio_summary()

    try:
        account = alpaca_client.get_account()

        if not account:
            return None

        equity = float(account.get('equity', 0))
        cash = float(account.get('cash', 0))
        positions_value = equity - cash

        # Calculate daily P&L
        last_equity = float(account.get('last_equity', equity))
        daily_pnl = equity - last_equity
        daily_pnl_pct = (daily_pnl / last_equity * 100) if last_equity > 0 else 0

        # Get initial value for total return
        initial_value = settings.initial_cash if hasattr(settings, 'initial_cash') else 100000
        total_return = equity - initial_value
        total_return_pct = (total_return / initial_value * 100) if initial_value > 0 else 0

        # Get position count
        positions = alpaca_client.get_positions()
        num_positions = len(positions) if positions else 0

        return {
            'total_value': equity,
            'cash': cash,
            'positions_value': positions_value,
            'daily_pnl': daily_pnl,
            'daily_pnl_pct': daily_pnl_pct,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'num_positions': num_positions,
        }

    except Exception as e:
        print(f"Error getting portfolio summary: {e}")
        return _get_mock_portfolio_summary()


def _get_mock_portfolio_summary() -> Dict[str, Any]:
    """Return mock portfolio summary when API not available."""
    return {
        'total_value': 100000.0,
        'cash': 100000.0,
        'positions_value': 0.0,
        'daily_pnl': 0.0,
        'daily_pnl_pct': 0.0,
        'total_return': 0.0,
        'total_return_pct': 0.0,
        'num_positions': 0,
    }


def get_positions() -> List[Dict[str, Any]]:
    """Get current positions from Alpaca."""
    if not ALPACA_AVAILABLE:
        return []

    try:
        positions = alpaca_client.get_positions()

        if not positions:
            return []

        result = []
        for pos in positions:
            result.append({
                'symbol': pos.get('symbol'),
                'quantity': float(pos.get('qty', 0)),
                'avg_entry_price': float(pos.get('avg_entry_price', 0)),
                'current_price': float(pos.get('current_price', 0)),
                'market_value': float(pos.get('market_value', 0)),
                'unrealized_pnl': float(pos.get('unrealized_pl', 0)),
                'unrealized_pnl_pct': float(pos.get('unrealized_plpc', 0)) * 100,
            })

        return result

    except Exception as e:
        print(f"Error getting positions: {e}")
        return []


def get_recent_trades(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent trades from database or backtest files."""
    # First try database
    if DB_AVAILABLE:
        try:
            db = SessionLocal()
            trades = db.query(Trade).order_by(Trade.executed_at.desc()).limit(limit).all()

            result = []
            for trade in trades:
                result.append({
                    'timestamp': trade.executed_at,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'quantity': trade.quantity,
                    'price': trade.filled_price,
                    'value': trade.quantity * trade.filled_price,
                    'reason': trade.notes or '',
                })

            db.close()

            if result:
                return result

        except Exception as e:
            print(f"Error getting trades from DB: {e}")

    # Fall back to backtest trades
    return _get_backtest_trades(limit)


def _get_backtest_trades(limit: int = 20) -> List[Dict[str, Any]]:
    """Load trades from most recent backtest file."""
    data_dir = Path("data")

    if not data_dir.exists():
        return []

    # Find most recent trades file
    trade_files = sorted(data_dir.glob("backtest_trades_*.csv"), reverse=True)

    if not trade_files:
        return []

    try:
        df = pd.read_csv(trade_files[0])
        df = df.tail(limit)

        result = []
        for _, row in df.iterrows():
            result.append({
                'date': row.get('date'),
                'symbol': row.get('symbol'),
                'side': row.get('side'),
                'quantity': row.get('quantity'),
                'price': row.get('price'),
                'value': row.get('value'),
                'reason': row.get('reason', ''),
            })

        return result

    except Exception as e:
        print(f"Error loading backtest trades: {e}")
        return []


def get_equity_curve() -> pd.DataFrame:
    """Get equity curve data."""
    # First try to get from database snapshots
    if DB_AVAILABLE:
        try:
            # This would require a PortfolioSnapshot model
            pass
        except Exception:
            pass

    # Fall back to backtest equity files
    data_dir = Path("data")

    if not data_dir.exists():
        return pd.DataFrame()

    # Find most recent equity file
    equity_files = sorted(data_dir.glob("backtest_equity_*.csv"), reverse=True)

    if not equity_files:
        return pd.DataFrame()

    try:
        df = pd.read_csv(equity_files[0])
        df['date'] = pd.to_datetime(df['date'])
        return df

    except Exception as e:
        print(f"Error loading equity curve: {e}")
        return pd.DataFrame()


def get_backtest_results() -> List[Path]:
    """Get list of available backtest result files."""
    data_dir = Path("data")

    if not data_dir.exists():
        return []

    # Find equity files (they have the main results)
    equity_files = sorted(data_dir.glob("backtest_equity_*.csv"), reverse=True)

    return equity_files


def get_performance_metrics() -> Dict[str, Any]:
    """Calculate performance metrics from equity curve."""
    df = get_equity_curve()

    if df.empty:
        return {}

    try:
        # Basic metrics
        start_value = df['total_value'].iloc[0]
        end_value = df['total_value'].iloc[-1]
        total_return_pct = ((end_value - start_value) / start_value) * 100

        # Daily returns
        df['returns'] = df['total_value'].pct_change()
        daily_returns = df['returns'].dropna()

        # Sharpe ratio (annualized, assuming 252 trading days)
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * (252 ** 0.5)
        else:
            sharpe_ratio = 0

        # Sortino ratio (using downside deviation)
        negative_returns = daily_returns[daily_returns < 0]
        if len(negative_returns) > 1 and negative_returns.std() > 0:
            sortino_ratio = (daily_returns.mean() / negative_returns.std()) * (252 ** 0.5)
        else:
            sortino_ratio = 0

        # Max drawdown
        rolling_max = df['total_value'].cummax()
        drawdown = (df['total_value'] - rolling_max) / rolling_max * 100
        max_drawdown_pct = abs(drawdown.min())

        # Get trade stats from trades file
        trades = get_recent_trades(limit=1000)
        total_trades = len(trades)
        winning_trades = 0
        profit_sum = 0
        loss_sum = 0

        # Calculate win rate from buy/sell pairs
        # This is a simplified calculation
        if trades:
            buy_trades = [t for t in trades if t.get('side', '').lower() == 'buy']
            sell_trades = [t for t in trades if t.get('side', '').lower() == 'sell']

            # Match trades (simplified - assumes FIFO)
            for i, sell in enumerate(sell_trades):
                if i < len(buy_trades):
                    buy = buy_trades[i]
                    if buy.get('symbol') == sell.get('symbol'):
                        profit = (sell.get('price', 0) - buy.get('price', 0)) * buy.get('quantity', 0)
                        if profit > 0:
                            winning_trades += 1
                            profit_sum += profit
                        else:
                            loss_sum += abs(profit)

        completed_trades = min(len([t for t in trades if t.get('side', '').lower() == 'sell']),
                               len([t for t in trades if t.get('side', '').lower() == 'buy']))
        win_rate_pct = (winning_trades / completed_trades * 100) if completed_trades > 0 else 0
        profit_factor = (profit_sum / loss_sum) if loss_sum > 0 else profit_sum if profit_sum > 0 else 0
        avg_trade_pct = total_return_pct / completed_trades if completed_trades > 0 else 0

        return {
            'total_return_pct': total_return_pct,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown_pct': max_drawdown_pct,
            'win_rate_pct': win_rate_pct,
            'profit_factor': profit_factor,
            'total_trades': total_trades,
            'avg_trade_pct': avg_trade_pct,
        }

    except Exception as e:
        print(f"Error calculating metrics: {e}")
        return {}


def get_daily_pnl_history(days: int = 30) -> pd.DataFrame:
    """Get daily P&L history."""
    df = get_equity_curve()

    if df.empty:
        return pd.DataFrame()

    # Calculate daily P&L
    df['daily_pnl'] = df['total_value'].diff()
    df['daily_pnl_pct'] = df['total_value'].pct_change() * 100

    # Get last N days
    df = df.tail(days)

    return df[['date', 'daily_pnl', 'daily_pnl_pct']]


def get_wsb_trending() -> List[Dict[str, Any]]:
    """Get WSB trending stocks from Quiver Quant."""
    if not SENTIMENT_AVAILABLE:
        return []

    try:
        return quiver_provider.get_top_mentioned(limit=15)
    except Exception as e:
        print(f"Error getting WSB trending: {e}")
        return []


def get_stocktwits_trending() -> List[Dict[str, Any]]:
    """Get StockTwits trending stocks."""
    if not SENTIMENT_AVAILABLE:
        return []

    try:
        return stocktwits_provider.get_trending()
    except Exception as e:
        print(f"Error getting StockTwits trending: {e}")
        return []


def get_symbol_sentiment(symbol: str) -> Dict[str, Any]:
    """Get aggregated sentiment for a symbol."""
    if not SENTIMENT_AVAILABLE:
        return {}

    try:
        sentiment = sentiment_aggregator.get_sentiment(symbol, include_news=False)
        return {
            'symbol': sentiment.symbol,
            'overall_score': sentiment.overall_score,
            'overall_label': sentiment.overall_label,
            'confidence': sentiment.confidence,
            'wsb_mentions': sentiment.wsb_mentions,
            'wsb_score': sentiment.wsb_score,
            'wsb_trending': sentiment.wsb_trending,
            'stocktwits_score': sentiment.stocktwits_score,
            'stocktwits_bullish_pct': sentiment.stocktwits_bullish_pct,
        }
    except Exception as e:
        print(f"Error getting sentiment for {symbol}: {e}")
        return {}


def get_market_mood() -> Dict[str, Any]:
    """Get overall market mood from sentiment sources."""
    if not SENTIMENT_AVAILABLE:
        return {'mood': 'Unknown', 'emoji': '❓'}

    try:
        return sentiment_aggregator.get_market_mood()
    except Exception as e:
        print(f"Error getting market mood: {e}")
        return {'mood': 'Unknown', 'emoji': '❓'}
