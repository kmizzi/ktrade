#!/usr/bin/env python3
"""
Backfill database with historical data from Alpaca API.
Fetches portfolio history, orders, and positions to populate the database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config.settings import settings
from src.database.session import SessionLocal
from src.database.models import (
    Position, Trade, PortfolioSnapshot,
    PositionStatus, TradeSide
)


def get_alpaca_clients():
    """Initialize Alpaca clients."""
    trading = TradingClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key,
        paper=settings.is_paper_trading
    )
    data = StockHistoricalDataClient(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_secret_key
    )
    return trading, data


def backfill_portfolio_history(trading_client, db):
    """Backfill portfolio snapshots from Alpaca account activities."""
    print("\n=== Backfilling Portfolio History ===")

    try:
        # Get portfolio history
        history = trading_client.get_portfolio_history(
            period="1Y",
            timeframe="1D"
        )

        # Check if we got data
        if history.timestamp is None or len(history.timestamp) == 0:
            print("No portfolio history data available")
            return 0

        count = 0
        for i, ts in enumerate(history.timestamp):
            timestamp = datetime.fromtimestamp(ts)
            equity = float(history.equity[i]) if history.equity[i] else 0

            # Check if snapshot already exists
            existing = db.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.timestamp == timestamp
            ).first()

            if existing:
                continue

            # Get profit_loss_pct for the day
            daily_return = None
            if history.profit_loss_pct and i < len(history.profit_loss_pct):
                daily_return = float(history.profit_loss_pct[i]) * 100 if history.profit_loss_pct[i] else None

            snapshot = PortfolioSnapshot(
                timestamp=timestamp,
                total_value=equity,
                cash=0,  # Not available in history
                positions_value=equity,  # Approximate
                daily_return_pct=daily_return,
                position_count=0,
                open_positions_count=0
            )
            db.add(snapshot)
            count += 1

        db.commit()
        print(f"Added {count} portfolio snapshots")
        return count

    except Exception as e:
        print(f"Error fetching portfolio history: {e}")
        db.rollback()
        return 0


def backfill_orders_and_trades(trading_client, db):
    """Backfill positions and trades from Alpaca order history."""
    print("\n=== Backfilling Orders and Trades ===")

    try:
        # Get all filled orders
        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500,
            nested=True
        )
        orders = trading_client.get_orders(request)

        print(f"Found {len(orders)} closed orders")

        # Group orders by symbol to create positions
        positions_map = {}  # symbol -> list of orders

        for order in orders:
            if order.filled_qty and float(order.filled_qty) > 0:
                symbol = order.symbol
                if symbol not in positions_map:
                    positions_map[symbol] = []
                positions_map[symbol].append(order)

        positions_created = 0
        trades_created = 0

        for symbol, symbol_orders in positions_map.items():
            # Sort by filled_at
            symbol_orders.sort(key=lambda x: x.filled_at if x.filled_at else x.submitted_at)

            # Create a position for each buy order (simplified approach)
            current_position = None

            for order in symbol_orders:
                filled_at = order.filled_at if order.filled_at else order.submitted_at
                filled_price = float(order.filled_avg_price) if order.filled_avg_price else 0
                filled_qty = float(order.filled_qty) if order.filled_qty else 0
                side = order.side.value.lower()

                if side == "buy":
                    # Check if position with this order_id exists
                    existing = db.query(Position).filter(
                        Position.alpaca_order_id == str(order.id)
                    ).first()

                    if existing:
                        current_position = existing
                        continue

                    # Create new position
                    position = Position(
                        symbol=symbol,
                        platform="alpaca",
                        quantity=filled_qty,
                        entry_price=filled_price,
                        entry_date=filled_at,
                        strategy="unknown",
                        status=PositionStatus.OPEN,
                        alpaca_order_id=str(order.id)
                    )
                    db.add(position)
                    db.flush()  # Get ID

                    current_position = position
                    positions_created += 1

                    # Create trade record
                    trade = Trade(
                        position_id=position.id,
                        symbol=symbol,
                        side=TradeSide.BUY,
                        quantity=filled_qty,
                        price=filled_price,
                        filled_at=filled_at,
                        alpaca_order_id=str(order.id),
                        alpaca_client_order_id=order.client_order_id
                    )
                    db.add(trade)
                    trades_created += 1

                elif side == "sell" and current_position:
                    # Close or partially close position
                    current_position.exit_price = filled_price
                    current_position.exit_date = filled_at
                    current_position.status = PositionStatus.CLOSED

                    # Create trade record
                    trade = Trade(
                        position_id=current_position.id,
                        symbol=symbol,
                        side=TradeSide.SELL,
                        quantity=filled_qty,
                        price=filled_price,
                        filled_at=filled_at,
                        alpaca_order_id=str(order.id),
                        alpaca_client_order_id=order.client_order_id
                    )
                    db.add(trade)
                    trades_created += 1

                    current_position = None

        db.commit()
        print(f"Created {positions_created} positions and {trades_created} trades")
        return positions_created, trades_created

    except Exception as e:
        print(f"Error backfilling orders: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return 0, 0


def sync_current_positions(trading_client, db):
    """Sync current open positions from Alpaca."""
    print("\n=== Syncing Current Positions ===")

    try:
        positions = trading_client.get_all_positions()
        print(f"Found {len(positions)} open positions on Alpaca")

        count = 0
        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            avg_price = float(pos.avg_entry_price)

            # Check if we have an open position for this symbol
            existing = db.query(Position).filter(
                Position.symbol == symbol,
                Position.status == PositionStatus.OPEN
            ).first()

            if existing:
                # Update existing
                existing.quantity = qty
                existing.entry_price = avg_price
            else:
                # Create new
                position = Position(
                    symbol=symbol,
                    platform="alpaca",
                    quantity=qty,
                    entry_price=avg_price,
                    entry_date=datetime.utcnow(),
                    strategy="synced",
                    status=PositionStatus.OPEN
                )
                db.add(position)
                count += 1

        db.commit()
        print(f"Added/updated {count} current positions")
        return count

    except Exception as e:
        print(f"Error syncing positions: {e}")
        db.rollback()
        return 0


def create_current_snapshot(trading_client, db):
    """Create a current portfolio snapshot."""
    print("\n=== Creating Current Snapshot ===")

    try:
        account = trading_client.get_account()
        positions = trading_client.get_all_positions()

        total_value = float(account.portfolio_value)
        cash = float(account.cash)
        positions_value = sum(float(p.market_value) for p in positions)

        # Check if snapshot for today exists
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = db.query(PortfolioSnapshot).filter(
            PortfolioSnapshot.timestamp >= today
        ).first()

        if existing:
            # Update
            existing.total_value = total_value
            existing.cash = cash
            existing.positions_value = positions_value
            existing.position_count = len(positions)
            existing.open_positions_count = len(positions)
            print("Updated today's snapshot")
        else:
            # Create new
            snapshot = PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_value=total_value,
                cash=cash,
                positions_value=positions_value,
                position_count=len(positions),
                open_positions_count=len(positions)
            )
            db.add(snapshot)
            print("Created new snapshot")

        db.commit()
        print(f"Portfolio: ${total_value:,.2f} (${cash:,.2f} cash)")
        return 1

    except Exception as e:
        print(f"Error creating snapshot: {e}")
        db.rollback()
        return 0


def main():
    print("=" * 50)
    print("KTrade Database Backfill")
    print("=" * 50)

    # Initialize
    trading_client, data_client = get_alpaca_clients()
    db = SessionLocal()

    try:
        # 1. Backfill portfolio history
        backfill_portfolio_history(trading_client, db)

        # 2. Backfill orders and trades
        backfill_orders_and_trades(trading_client, db)

        # 3. Sync current positions
        sync_current_positions(trading_client, db)

        # 4. Create current snapshot
        create_current_snapshot(trading_client, db)

        # Print summary
        print("\n" + "=" * 50)
        print("Summary:")
        print(f"  Positions: {db.query(Position).count()}")
        print(f"  Trades: {db.query(Trade).count()}")
        print(f"  Snapshots: {db.query(PortfolioSnapshot).count()}")
        print("=" * 50)

    finally:
        db.close()


if __name__ == "__main__":
    main()
