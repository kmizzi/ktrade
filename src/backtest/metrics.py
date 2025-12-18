"""
Performance metrics calculator for backtesting.
Calculates key trading metrics like Sharpe ratio, max drawdown, win rate, etc.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import math
import structlog

from src.backtest.portfolio import SimulatedPortfolio, SimulatedTrade, PortfolioSnapshot

logger = structlog.get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Container for all performance metrics."""
    # Returns
    total_return_pct: float
    annualized_return_pct: float

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: int
    volatility_pct: float

    # Trading metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    avg_trade_duration_days: float

    # P&L
    total_profit: float
    total_loss: float
    net_profit: float

    # Portfolio
    final_value: float
    initial_value: float

    def __str__(self) -> str:
        """Human-readable summary."""
        return f"""
============================================================
                    BACKTEST RESULTS
============================================================

RETURNS
-------
Total Return:        {self.total_return_pct:>10.2f}%
Annualized Return:   {self.annualized_return_pct:>10.2f}%
Net Profit:          ${self.net_profit:>10,.2f}

RISK METRICS
------------
Sharpe Ratio:        {self.sharpe_ratio:>10.2f}
Sortino Ratio:       {self.sortino_ratio:>10.2f}
Max Drawdown:        {self.max_drawdown_pct:>10.2f}%
Max DD Duration:     {self.max_drawdown_duration_days:>10} days
Volatility:          {self.volatility_pct:>10.2f}%

TRADING METRICS
---------------
Total Trades:        {self.total_trades:>10}
Winning Trades:      {self.winning_trades:>10}
Losing Trades:       {self.losing_trades:>10}
Win Rate:            {self.win_rate_pct:>10.2f}%
Avg Win:             {self.avg_win_pct:>10.2f}%
Avg Loss:            {self.avg_loss_pct:>10.2f}%
Profit Factor:       {self.profit_factor:>10.2f}

PORTFOLIO
---------
Initial Value:       ${self.initial_value:>10,.2f}
Final Value:         ${self.final_value:>10,.2f}
============================================================
"""


def calculate_metrics(
    portfolio: SimulatedPortfolio,
    trading_days: int = 252,
    risk_free_rate: float = 0.05
) -> PerformanceMetrics:
    """
    Calculate all performance metrics from a backtest.

    Args:
        portfolio: The simulated portfolio after backtest
        trading_days: Trading days per year (default: 252)
        risk_free_rate: Annual risk-free rate (default: 5%)

    Returns:
        PerformanceMetrics object with all calculated metrics
    """
    snapshots = portfolio.snapshots
    trades = portfolio.trades

    if not snapshots:
        return _empty_metrics(portfolio.initial_cash)

    # Calculate returns
    initial_value = portfolio.initial_cash
    final_value = snapshots[-1].total_value
    total_return_pct = ((final_value - initial_value) / initial_value) * 100

    # Calculate days in backtest
    days = (snapshots[-1].timestamp - snapshots[0].timestamp).days
    years = max(days / 365, 0.01)  # Avoid division by zero

    # Annualized return
    if total_return_pct >= 0:
        annualized_return = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100
    else:
        annualized_return = -((1 + abs(total_return_pct) / 100) ** (1 / years) - 1) * 100

    # Daily returns for volatility calculation
    daily_returns = [s.daily_return_pct for s in snapshots if s.daily_return_pct != 0]

    if daily_returns:
        volatility = _calculate_std(daily_returns) * math.sqrt(trading_days)
    else:
        volatility = 0.0

    # Sharpe Ratio
    if volatility > 0:
        sharpe = (annualized_return - risk_free_rate * 100) / volatility
    else:
        sharpe = 0.0

    # Sortino Ratio (uses downside deviation)
    negative_returns = [r for r in daily_returns if r < 0]
    if negative_returns:
        downside_dev = _calculate_std(negative_returns) * math.sqrt(trading_days)
        sortino = (annualized_return - risk_free_rate * 100) / downside_dev if downside_dev > 0 else 0
    else:
        sortino = sharpe  # No negative returns

    # Max Drawdown
    max_dd, max_dd_duration = _calculate_max_drawdown(snapshots)

    # Trade analysis
    trade_stats = _analyze_trades(trades, portfolio)

    return PerformanceMetrics(
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized_return,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_pct=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        volatility_pct=volatility,
        total_trades=trade_stats['total_trades'],
        winning_trades=trade_stats['winning_trades'],
        losing_trades=trade_stats['losing_trades'],
        win_rate_pct=trade_stats['win_rate'],
        avg_win_pct=trade_stats['avg_win'],
        avg_loss_pct=trade_stats['avg_loss'],
        profit_factor=trade_stats['profit_factor'],
        avg_trade_duration_days=trade_stats['avg_duration'],
        total_profit=trade_stats['total_profit'],
        total_loss=trade_stats['total_loss'],
        net_profit=final_value - initial_value,
        final_value=final_value,
        initial_value=initial_value
    )


def _calculate_std(values: List[float]) -> float:
    """Calculate standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _calculate_max_drawdown(snapshots: List[PortfolioSnapshot]) -> tuple:
    """
    Calculate maximum drawdown and its duration.

    Returns:
        Tuple of (max_drawdown_pct, max_drawdown_duration_days)
    """
    if not snapshots:
        return 0.0, 0

    peak = snapshots[0].total_value
    max_drawdown = 0.0
    max_dd_duration = 0
    current_dd_start = None
    peak_timestamp = snapshots[0].timestamp

    for snapshot in snapshots:
        if snapshot.total_value > peak:
            peak = snapshot.total_value
            peak_timestamp = snapshot.timestamp
            current_dd_start = None
        else:
            drawdown = ((peak - snapshot.total_value) / peak) * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                if current_dd_start is None:
                    current_dd_start = peak_timestamp
                max_dd_duration = (snapshot.timestamp - current_dd_start).days

    return max_drawdown, max_dd_duration


def _analyze_trades(
    trades: List[SimulatedTrade],
    portfolio: SimulatedPortfolio
) -> Dict[str, Any]:
    """
    Analyze trades to calculate win rate, profit factor, etc.
    """
    if not trades:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'avg_duration': 0.0,
            'total_profit': 0.0,
            'total_loss': 0.0
        }

    # Match buys with sells to calculate trade P&L
    completed_trades = []
    open_positions: Dict[str, List[SimulatedTrade]] = {}

    for trade in trades:
        if trade.side == 'buy':
            if trade.symbol not in open_positions:
                open_positions[trade.symbol] = []
            open_positions[trade.symbol].append(trade)
        elif trade.side == 'sell':
            if trade.symbol in open_positions and open_positions[trade.symbol]:
                buy_trade = open_positions[trade.symbol].pop(0)
                pnl_pct = ((trade.price - buy_trade.price) / buy_trade.price) * 100
                duration = (trade.timestamp - buy_trade.timestamp).days
                completed_trades.append({
                    'symbol': trade.symbol,
                    'pnl_pct': pnl_pct,
                    'pnl_value': (trade.price - buy_trade.price) * trade.quantity,
                    'duration_days': duration
                })

    if not completed_trades:
        return {
            'total_trades': len(trades) // 2,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'profit_factor': 0.0,
            'avg_duration': 0.0,
            'total_profit': 0.0,
            'total_loss': 0.0
        }

    # Calculate metrics
    wins = [t for t in completed_trades if t['pnl_pct'] > 0]
    losses = [t for t in completed_trades if t['pnl_pct'] <= 0]

    total_profit = sum(t['pnl_value'] for t in wins)
    total_loss = abs(sum(t['pnl_value'] for t in losses))

    win_rate = (len(wins) / len(completed_trades)) * 100 if completed_trades else 0
    avg_win = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    avg_duration = sum(t['duration_days'] for t in completed_trades) / len(completed_trades)

    return {
        'total_trades': len(completed_trades),
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'avg_duration': avg_duration,
        'total_profit': total_profit,
        'total_loss': total_loss
    }


def _empty_metrics(initial_value: float) -> PerformanceMetrics:
    """Return empty metrics when no data available."""
    return PerformanceMetrics(
        total_return_pct=0.0,
        annualized_return_pct=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown_pct=0.0,
        max_drawdown_duration_days=0,
        volatility_pct=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate_pct=0.0,
        avg_win_pct=0.0,
        avg_loss_pct=0.0,
        profit_factor=0.0,
        avg_trade_duration_days=0.0,
        total_profit=0.0,
        total_loss=0.0,
        net_profit=0.0,
        final_value=initial_value,
        initial_value=initial_value
    )


def generate_report(
    metrics: PerformanceMetrics,
    portfolio: SimulatedPortfolio,
    strategy_name: str = "Unknown"
) -> str:
    """
    Generate a detailed backtest report.

    Args:
        metrics: Calculated performance metrics
        portfolio: The portfolio with trade history
        strategy_name: Name of the strategy tested

    Returns:
        Formatted report string
    """
    report = [str(metrics)]

    # Add trade log
    report.append("\nTRADE LOG (Last 20 trades)")
    report.append("-" * 60)

    for trade in portfolio.trades[-20:]:
        report.append(
            f"{trade.timestamp.strftime('%Y-%m-%d')} | "
            f"{trade.side.upper():4} | "
            f"{trade.symbol:5} | "
            f"Qty: {trade.quantity:>6.0f} | "
            f"Price: ${trade.price:>8.2f} | "
            f"{trade.reason}"
        )

    return "\n".join(report)
