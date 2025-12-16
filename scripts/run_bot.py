"""
Main trading bot runner.
Orchestrates strategy evaluation, signal generation, and trade execution.
"""

import sys
from pathlib import Path
from datetime import datetime
import signal as sys_signal
import time
import threading

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
from src.api.alpaca_client import alpaca_client, RateLimitException
from src.data.stock_scanner import stock_scanner

# Setup logging
logger = setup_logging()

# Initialize strategies
strategies = []
if settings.enable_simple_momentum:
    strategies.append(SimpleMomentumStrategy(enabled=True))

# Scheduler
scheduler = BlockingScheduler()

# Lock to prevent concurrent strategy cycles
_strategy_cycle_lock = threading.Lock()
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

        # Sync positions with Alpaca and ensure trailing stops are set
        db = get_db_session()
        try:
            order_executor.sync_positions_with_alpaca(db)

            # Refresh trailing stops for fractional shares (DAY orders expire overnight)
            refreshed = order_executor.refresh_trailing_stops_for_fractional_shares(db)
            if refreshed > 0:
                logger.info("trailing_stops_refreshed_at_market_open", count=refreshed)

            # Ensure all positions have trailing stop orders on Alpaca
            stops_added = order_executor.ensure_all_positions_have_trailing_stops(db)
            if stops_added > 0:
                logger.info("trailing_stops_added_at_market_open", count=stops_added)
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

            # Get currently owned symbols from Alpaca
            positions = alpaca_client.get_positions()
            owned_symbols = [pos['symbol'] for pos in positions]

            logger.info(
                "evaluating_watchlist",
                symbols=watchlist,
                strategy_count=len(strategies),
                watchlist_size=len(watchlist),
                owned_symbols=owned_symbols,
                dynamic_discovery=settings.enable_dynamic_discovery
            )

            all_signals = []

            # Generate signals from each strategy
            for strategy in strategies:
                if not strategy.is_enabled():
                    continue

                try:
                    signals = strategy.generate_signals(watchlist, owned_symbols=owned_symbols)
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

            # Deduplicate by symbol - only execute one signal per symbol
            seen_symbols = set()
            deduplicated_signals = []
            for signal in signals:
                if signal.symbol not in seen_symbols:
                    seen_symbols.add(signal.symbol)
                    deduplicated_signals.append(signal)
                else:
                    # Mark duplicate signal as executed to prevent retry
                    signal.executed = True
                    logger.info("skipping_duplicate_signal", symbol=signal.symbol)

            db.commit()

            for signal in deduplicated_signals:
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
                        # Signal was skipped (already have position, risk limit, etc.)
                        # This is normal behavior, not a failure - don't log as warning
                        logger.info(
                            "signal_skipped",
                            symbol=signal.symbol,
                            reason="position_exists_or_risk_limit"
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


def process_sell_signals():
    """
    Process SELL signals by tightening trailing stops on profitable positions.

    When momentum indicators suggest weakness, we don't immediately sell,
    but we tighten the trailing stop to lock in more profits if the price drops.
    """
    logger.info("sell_signal_processing_started")

    try:
        db = get_db_session()
        try:
            # Get unprocessed SELL signals
            sell_signals = db.query(Signal).filter(
                Signal.executed == False,
                Signal.signal_type == SignalType.SELL,
                Signal.confidence >= 0.7  # Only act on higher confidence SELL signals
            ).all()

            if not sell_signals:
                logger.info("no_sell_signals_to_process")
                return

            logger.info("sell_signals_to_process", count=len(sell_signals))

            # Get Alpaca positions for current prices
            alpaca_positions = {p['symbol']: p for p in alpaca_client.get_positions()}

            for signal in sell_signals:
                try:
                    symbol = signal.symbol

                    # Check if we have an Alpaca position
                    alpaca_pos = alpaca_positions.get(symbol)
                    if not alpaca_pos:
                        # Mark as executed since we don't own it
                        signal.executed = True
                        continue

                    # Get matching DB position
                    position = db.query(Position).filter(
                        Position.symbol == symbol,
                        Position.status == PositionStatus.OPEN
                    ).first()

                    if not position:
                        signal.executed = True
                        continue

                    current_price = alpaca_pos['current_price']
                    entry_price = position.entry_price
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100

                    logger.info(
                        "processing_sell_signal",
                        symbol=symbol,
                        confidence=signal.confidence,
                        pnl_pct=pnl_pct,
                        reason=signal.notes
                    )

                    # Only tighten if profitable
                    if pnl_pct > 0:
                        success = order_executor.tighten_trailing_stop(
                            position=position,
                            db=db,
                            new_trail_percent=settings.tightened_trailing_stop_pct,
                            current_price=current_price
                        )

                        if success:
                            logger.info(
                                "trailing_stop_tightened_on_sell_signal",
                                symbol=symbol,
                                new_trail_pct=settings.tightened_trailing_stop_pct,
                                pnl_pct=pnl_pct,
                                reason=signal.notes
                            )
                    else:
                        logger.info(
                            "skip_tighten_position_not_profitable",
                            symbol=symbol,
                            pnl_pct=pnl_pct
                        )

                    # Mark signal as executed
                    signal.executed = True

                except Exception as e:
                    logger.error(
                        "failed_to_process_sell_signal",
                        symbol=signal.symbol,
                        error=str(e)
                    )

            db.commit()

        finally:
            db.close()

    except Exception as e:
        logger.error("sell_signal_processing_error", error=str(e))


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
    # Prevent concurrent cycles from running
    if not _strategy_cycle_lock.acquire(blocking=False):
        logger.warning("strategy_cycle_already_running_skipping")
        return

    try:
        # First evaluate strategies and generate signals
        evaluate_strategies()

        # Execute BUY signals
        execute_signals()

        # Process SELL signals (tighten trailing stops on profitable positions)
        process_sell_signals()

        # Finally monitor existing positions
        monitor_positions()

    except Exception as e:
        logger.error("strategy_cycle_error", error=str(e))
    finally:
        _strategy_cycle_lock.release()


def run_perpetual_strategy_loop():
    """
    Run strategy cycles perpetually during market hours.
    Only backs off when hitting Alpaca rate limits (429 errors).
    """
    global shutdown_requested

    cycle_count = 0

    while not shutdown_requested:
        try:
            # Check if market is open
            if not alpaca_client.is_market_open():
                # Market closed - wait and check again
                clock = alpaca_client.get_clock()
                next_open = clock.get('next_open')
                logger.info(
                    "market_closed_waiting",
                    next_open=str(next_open) if next_open else "unknown"
                )
                # Sleep for 60 seconds before checking again
                time.sleep(60)
                continue

            # Run a strategy cycle
            cycle_count += 1
            logger.info("perpetual_cycle_starting", cycle=cycle_count)

            run_strategy_cycle()

            logger.info("perpetual_cycle_completed", cycle=cycle_count)

            # No sleep - immediately start next cycle
            # Rate limiting is handled reactively via RateLimitException

        except RateLimitException as e:
            # Alpaca rate limit hit - back off for the specified time
            logger.warning(
                "rate_limit_backoff",
                retry_after=e.retry_after,
                cycle=cycle_count
            )
            time.sleep(e.retry_after)

        except Exception as e:
            # Log error but keep running
            logger.error("perpetual_cycle_error", error=str(e), cycle=cycle_count)
            # Brief pause on error to prevent tight error loop
            time.sleep(5)


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

        # Schedule market open/close tasks (all times in US Eastern)
        # Market open: 9:30 AM ET
        scheduler.add_job(
            market_open_tasks,
            CronTrigger(day_of_week='mon-fri', hour=9, minute=30, timezone='America/New_York'),
            id='market_open_tasks'
        )

        # Market close: 4:00 PM ET
        scheduler.add_job(
            market_close_tasks,
            CronTrigger(day_of_week='mon-fri', hour=16, minute=0, timezone='America/New_York'),
            id='market_close_tasks'
        )

        # Portfolio sync every hour
        scheduler.add_job(
            sync_portfolio,
            CronTrigger(minute=0),
            id='sync_portfolio'
        )

        # Run initial tasks
        logger.info("running_initial_tasks")
        sync_portfolio()

        # Start scheduler in a background thread (for market open/close tasks)
        from apscheduler.schedulers.background import BackgroundScheduler
        bg_scheduler = BackgroundScheduler()
        for job in scheduler.get_jobs():
            bg_scheduler.add_job(
                job.func,
                job.trigger,
                id=job.id
            )
        bg_scheduler.start()
        logger.info("scheduler_started")

        # Run perpetual strategy loop (main thread)
        logger.info("starting_perpetual_strategy_loop")
        logger.info("bot_running_press_ctrl_c_to_stop")

        run_perpetual_strategy_loop()

    except (KeyboardInterrupt, SystemExit):
        logger.info("bot_shutdown_requested")
    except Exception as e:
        logger.error("bot_error", error=str(e))
    finally:
        shutdown_requested = True
        try:
            bg_scheduler.shutdown(wait=False)
        except NameError:
            pass  # bg_scheduler wasn't created yet
        except Exception:
            pass
        logger.info("bot_stopped")


if __name__ == "__main__":
    main()
