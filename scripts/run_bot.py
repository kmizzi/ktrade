"""
Main trading bot runner.
Orchestrates strategy evaluation, signal generation, and trade execution.
"""

import sys
from pathlib import Path
from datetime import datetime
import signal as sys_signal
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import structlog

from config.settings import settings
from src.utils.logger import setup_logging
from src.database.session import get_db_session, init_db
from src.database.models import Signal, Position, PositionStatus, SignalType
from src.strategies.simple_momentum import SimpleMomentumStrategy
from src.core.risk_manager import risk_manager
from src.core.order_executor import order_executor
from src.core.portfolio import portfolio_tracker
from src.api.alpaca_client import alpaca_client
from src.data.stock_scanner import stock_scanner

# Setup logging
logger = setup_logging()

# Initialize strategies
strategies = []
if settings.enable_simple_momentum:
    strategies.append(SimpleMomentumStrategy(enabled=True))

# Scheduler
scheduler = BlockingScheduler()
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global shutdown_requested
    logger.info("shutdown_signal_received", signal=signum)
    shutdown_requested = True
    scheduler.shutdown(wait=False)


def market_open_tasks():
    """Tasks to run at market open"""
    logger.info("market_open_tasks_started")

    try:
        # Reset daily risk tracking
        risk_manager.reset_daily_tracking()

        # Sync positions with Alpaca
        db = get_db_session()
        try:
            order_executor.sync_positions_with_alpaca(db)
        finally:
            db.close()

        # Generate fresh watchlist for the day
        if settings.enable_dynamic_discovery:
            logger.info("generating_fresh_watchlist_for_trading_day")
            watchlist = stock_scanner.get_dynamic_watchlist()
            logger.info(
                "daily_watchlist_generated",
                watchlist_size=len(watchlist),
                symbols=watchlist
            )

        logger.info("market_open_tasks_completed")

    except Exception as e:
        logger.error("market_open_tasks_failed", error=str(e))


def market_close_tasks():
    """Tasks to run at market close"""
    logger.info("market_close_tasks_started")

    try:
        # Save portfolio snapshot
        db = get_db_session()
        try:
            snapshot = portfolio_tracker.save_snapshot(db)
            if snapshot:
                # Log performance summary
                summary = portfolio_tracker.get_performance_summary(db, days=7)
                logger.info("performance_summary", **summary)
        finally:
            db.close()

        logger.info("market_close_tasks_completed")

    except Exception as e:
        logger.error("market_close_tasks_failed", error=str(e))


def evaluate_strategies():
    """Evaluate all enabled strategies and generate signals"""
    logger.info("strategy_evaluation_started")

    try:
        db = get_db_session()
        try:
            # Get dynamic watchlist from stock scanner
            watchlist = stock_scanner.get_watchlist()
            logger.info(
                "evaluating_watchlist",
                symbols=watchlist,
                strategy_count=len(strategies),
                watchlist_size=len(watchlist),
                dynamic_discovery=settings.enable_dynamic_discovery
            )

            all_signals = []

            # Generate signals from each strategy
            for strategy in strategies:
                if not strategy.is_enabled():
                    continue

                try:
                    signals = strategy.generate_signals(watchlist)
                    all_signals.extend(signals)

                    logger.info(
                        "strategy_evaluated",
                        strategy=strategy.name,
                        signals_count=len(signals)
                    )

                except Exception as e:
                    logger.error(
                        "strategy_evaluation_failed",
                        strategy=strategy.name,
                        error=str(e)
                    )

            # Save signals to database
            for signal in all_signals:
                db_signal = Signal(
                    symbol=signal.symbol,
                    timestamp=signal.timestamp,
                    strategy=signal.strategy_name,
                    signal_type=SignalType.BUY if signal.signal_type == 'buy' else SignalType.SELL,
                    confidence=signal.confidence,
                    data_snapshot=signal.data_snapshot,
                    executed=False
                )
                db.add(db_signal)

            db.commit()

            logger.info(
                "strategy_evaluation_completed",
                total_signals=len(all_signals)
            )

        finally:
            db.close()

    except Exception as e:
        logger.error("strategy_evaluation_error", error=str(e))


def execute_signals():
    """Execute buy signals from strategies"""
    logger.info("signal_execution_started")

    try:
        db = get_db_session()
        try:
            # Get unexecuted buy signals with high confidence
            signals = db.query(Signal).filter(
                Signal.executed == False,
                Signal.signal_type == SignalType.BUY,
                Signal.confidence >= 0.6
            ).order_by(Signal.confidence.desc()).limit(5).all()

            logger.info("signals_to_execute", count=len(signals))

            for signal in signals:
                try:
                    logger.info(
                        "executing_signal",
                        symbol=signal.symbol,
                        confidence=signal.confidence,
                        strategy=signal.strategy
                    )

                    position = order_executor.execute_buy_signal(signal, db)

                    if position:
                        logger.info(
                            "signal_executed_successfully",
                            symbol=signal.symbol,
                            position_id=position.id
                        )
                    else:
                        logger.warning(
                            "signal_execution_failed",
                            symbol=signal.symbol
                        )

                except Exception as e:
                    logger.error(
                        "failed_to_execute_signal",
                        signal_id=signal.id,
                        symbol=signal.symbol,
                        error=str(e)
                    )

        finally:
            db.close()

    except Exception as e:
        logger.error("signal_execution_error", error=str(e))


def monitor_positions():
    """Monitor open positions and check exit conditions"""
    logger.info("position_monitoring_started")

    try:
        db = get_db_session()
        try:
            # Get all open positions
            positions = db.query(Position).filter(
                Position.status == PositionStatus.OPEN
            ).all()

            logger.info("monitoring_positions", count=len(positions))

            for position in positions:
                try:
                    # Get current price
                    bars = alpaca_client.get_bars(position.symbol, timeframe="1Min", limit=1)
                    if not bars:
                        logger.warning("no_price_data", symbol=position.symbol)
                        continue

                    current_price = bars[-1]['close']

                    # Check risk management exit conditions
                    should_close_risk, risk_reason = risk_manager.should_close_position(
                        position, current_price
                    )

                    if should_close_risk:
                        logger.info(
                            "closing_position_risk",
                            position_id=position.id,
                            symbol=position.symbol,
                            reason=risk_reason
                        )
                        order_executor.close_position(position, risk_reason, db)
                        continue

                    # Check strategy exit conditions
                    strategy = next(
                        (s for s in strategies if s.name == position.strategy),
                        None
                    )

                    if strategy:
                        should_close_strategy, strategy_reason = strategy.should_exit_position(
                            position.symbol,
                            position.entry_price,
                            current_price
                        )

                        if should_close_strategy:
                            logger.info(
                                "closing_position_strategy",
                                position_id=position.id,
                                symbol=position.symbol,
                                reason=strategy_reason
                            )
                            order_executor.close_position(position, strategy_reason, db)

                except Exception as e:
                    logger.error(
                        "position_monitoring_failed",
                        position_id=position.id,
                        symbol=position.symbol,
                        error=str(e)
                    )

        finally:
            db.close()

    except Exception as e:
        logger.error("position_monitoring_error", error=str(e))


def sync_portfolio():
    """Sync portfolio with Alpaca and save snapshot"""
    logger.info("portfolio_sync_started")

    try:
        db = get_db_session()
        try:
            # Sync positions
            order_executor.sync_positions_with_alpaca(db)

            # Get current state
            state = portfolio_tracker.get_current_state()
            logger.info("portfolio_state", **state)

        finally:
            db.close()

    except Exception as e:
        logger.error("portfolio_sync_error", error=str(e))


def run_strategy_cycle():
    """Run a complete strategy evaluation cycle"""
    try:
        # First evaluate strategies and generate signals
        evaluate_strategies()

        # Then execute the signals
        execute_signals()

        # Finally monitor existing positions
        monitor_positions()

    except Exception as e:
        logger.error("strategy_cycle_error", error=str(e))


def main():
    """Main entry point"""
    global shutdown_requested

    logger.info(
        "trading_bot_starting",
        bot_mode=settings.bot_mode,
        environment=settings.environment,
        paper_trading=settings.is_paper_trading
    )

    # Register signal handlers
    sys_signal.signal(sys_signal.SIGINT, signal_handler)
    sys_signal.signal(sys_signal.SIGTERM, signal_handler)

    try:
        # Initialize database if needed
        init_db()
        logger.info("database_initialized")

        # Test Alpaca connection
        account = alpaca_client.get_account()
        logger.info(
            "alpaca_connected",
            portfolio_value=account['portfolio_value'],
            cash=account['cash']
        )

        # Schedule jobs
        # Market open: 9:30 AM ET (adjust for your timezone)
        scheduler.add_job(
            market_open_tasks,
            CronTrigger(day_of_week='mon-fri', hour=9, minute=30),
            id='market_open'
        )

        # Market close: 4:00 PM ET
        scheduler.add_job(
            market_close_tasks,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=0),
            id='market_close'
        )

        # Strategy evaluation and execution every 15 minutes during market hours
        # 9:30 AM to 4:00 PM ET, Monday-Friday
        scheduler.add_job(
            run_strategy_cycle,
            CronTrigger(day_of_week='mon-fri', hour='9-16', minute='*/15'),
            id='strategy_cycle'
        )

        # Portfolio sync every hour
        scheduler.add_job(
            sync_portfolio,
            CronTrigger(minute=0),
            id='portfolio_sync'
        )

        # Run initial tasks
        logger.info("running_initial_tasks")
        sync_portfolio()

        # Start scheduler
        logger.info("scheduler_started")
        logger.info("bot_running_press_ctrl_c_to_stop")

        scheduler.start()

    except (KeyboardInterrupt, SystemExit):
        logger.info("bot_shutdown_requested")
    except Exception as e:
        logger.error("bot_error", error=str(e))
    finally:
        if scheduler.running:
            scheduler.shutdown()
        logger.info("bot_stopped")


if __name__ == "__main__":
    main()
