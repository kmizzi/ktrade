# KTrade - Automated Trading Bot

An intelligent, automated trading bot that operates on **Alpaca** for both stocks and cryptocurrency using paper trading mode. The bot leverages multiple data sources including market data, technical indicators, and risk management to make informed trading decisions.

## Features

- **🎯 Autonomous Stock Discovery**: Bot finds hot stocks automatically using technical criteria
  - Top gainers detection
  - Volume spike identification
  - Technical breakout scanning
  - Dynamic watchlist generation (up to 20 stocks)
- **Multi-Asset Support**: Trade stocks and crypto through unified Alpaca API
- **Paper Trading**: Safe testing environment with Alpaca paper trading
- **Multiple Strategies**: Simple Momentum, DCA, Grid Trading, Sentiment-Momentum
- **Risk Management**: Position sizing, stop losses, daily loss limits, exposure caps
- **Real-time Monitoring**: Track positions, performance, and portfolio state
- **Structured Logging**: JSON-formatted logs for easy analysis
- **Database Tracking**: Complete audit trail of all trades and signals

## Architecture

```
ktrade/
├── config/          # Configuration and settings
├── src/
│   ├── api/         # Alpaca API client
│   ├── database/    # SQLAlchemy models
│   ├── strategies/  # Trading strategies
│   ├── core/        # Risk management, order execution, portfolio tracking
│   ├── data/        # Technical indicators
│   └── utils/       # Logging and helpers
├── scripts/         # Database init and bot runner
└── logs/            # Structured logs
```

## Prerequisites

- Python 3.11+
- Alpaca account with paper trading enabled
- API credentials from Alpaca

## Quick Start

### 1. Clone the Repository

```bash
cd /Users/kalvin/code/ktrade
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Your `.env` file is already set up with Alpaca credentials. Verify the configuration:

```bash
cat .env
```

Key settings:
- `ALPACA_API_KEY`: Your API key (already configured)
- `ALPACA_SECRET_KEY`: Your secret key (already configured)
- `ALPACA_BASE_URL`: Paper trading URL (already set to paper-api)
- `BOT_MODE`: Set to "paper" for paper trading
- `WATCHLIST_STOCKS`: Stocks to monitor (AAPL, MSFT, GOOGL, AMZN, TSLA)
- `WATCHLIST_CRYPTO`: Crypto to monitor (BTC/USD, ETH/USD)

### 5. Initialize Database

```bash
python scripts/init_db.py
```

This creates the SQLite database with all required tables.

### 6. Run the Bot

```bash
python scripts/run_bot.py
```

The bot will:
- Connect to Alpaca paper trading API
- Start monitoring your watchlist
- Evaluate trading strategies every 15 minutes during market hours
- Execute trades based on signals
- Monitor and close positions based on exit conditions
- Save portfolio snapshots

## Trading Strategies

### Simple Momentum Strategy (Enabled by default)

**Buy Conditions:**
- Price > 20-day SMA
- RSI between 40-70 (not overbought/oversold)

**Sell Conditions:**
- RSI > 75 (overbought)
- Price < 20-day SMA (trend reversal)
- Stop loss: -5% from entry

### DCA (Dollar-Cost Averaging) - Coming in Phase 1.2

Weekly scheduled buys + opportunistic dip buying

### Grid Trading - Coming in Phase 1.2

Buy at support, sell at resistance within defined ranges

### Sentiment-Momentum - Phase 2

Combines social media sentiment with price momentum

## Risk Management

The bot includes comprehensive risk controls:

- **Position Size Limit**: Max 10% of portfolio per position
- **Portfolio Exposure Cap**: Max 80% invested, 20% cash reserve
- **Daily Loss Limit**: Trading halts at -3% daily loss
- **Stop Losses**: Automatic -5% stop on all positions
- **Paper Trading**: No real money at risk

## Monitoring

### View Logs

```bash
# Real-time log monitoring
tail -f logs/ktrade_$(date +%Y%m%d).log

# Parse JSON logs
cat logs/ktrade_*.log | jq '.'

# Filter for trades
cat logs/ktrade_*.log | jq 'select(.event_type=="trade_executed")'
```

### Database Queries

```bash
# Open SQLite console
sqlite3 data/ktrade.db

# View open positions
SELECT symbol, strategy, quantity, entry_price,
       (quantity * entry_price) as value
FROM positions
WHERE status = 'open';

# View recent trades
SELECT symbol, side, quantity, price, filled_at
FROM trades
ORDER BY filled_at DESC
LIMIT 10;
```

### Alpaca Dashboard

Monitor your paper trading account at: https://app.alpaca.markets/paper/dashboard/overview

## Configuration

All configuration is in `.env`. Key parameters:

### Strategy Controls
```bash
ENABLE_SIMPLE_MOMENTUM=true
ENABLE_DCA=true
ENABLE_GRID_TRADING=true
ENABLE_SENTIMENT_MOMENTUM=false  # Phase 2
```

### Risk Parameters
```bash
MAX_POSITION_SIZE_PCT=10.0
MAX_PORTFOLIO_EXPOSURE_PCT=80.0
DAILY_LOSS_LIMIT_PCT=3.0
DEFAULT_STOP_LOSS_PCT=5.0
```

### Stock Discovery
```bash
ENABLE_DYNAMIC_DISCOVERY=true  # Autonomous stock finding
MAX_WATCHLIST_SIZE=20           # Max stocks in watchlist
MIN_STOCK_PRICE=5.0             # Minimum price filter
MIN_DAILY_VOLUME=1000000        # Minimum volume filter
TOP_GAINERS_COUNT=10            # Top gainers to include
TOP_VOLUME_COUNT=10             # High volume stocks

# Static Watchlist (fallback if discovery disabled)
WATCHLIST_STOCKS=AAPL,MSFT,GOOGL,AMZN,TSLA
WATCHLIST_CRYPTO=BTC/USD,ETH/USD
```

## Scheduled Tasks

The bot runs on a schedule:

- **Market Open (9:30 AM ET)**: Generate fresh watchlist, reset daily tracking, sync positions
- **Every 15 minutes (9:30 AM - 4:00 PM ET)**: Evaluate strategies on dynamic watchlist, execute signals, monitor positions
- **Every hour**: Sync portfolio with Alpaca
- **Market Close (4:00 PM ET)**: Save portfolio snapshot, log performance

### How Stock Discovery Works

At market open, the bot:
1. Scans 60+ liquid stocks across sectors
2. Identifies top gainers (e.g., MRK +3.84%)
3. Finds volume spikes (e.g., AVGO 3.58x normal volume)
4. Detects technical breakouts (50-day highs)
5. Combines best opportunities into dynamic watchlist (up to 20 stocks)
6. Evaluates these stocks every 15 minutes during trading hours

## Development Status

### ✅ Phase 1: Foundation (Completed)
- [x] Project structure and configuration
- [x] Alpaca API integration
- [x] Database models and session management
- [x] Structured logging
- [x] Simple Momentum strategy
- [x] Risk management system
- [x] Order execution engine
- [x] Portfolio tracking
- [x] Main bot runner with scheduling
- [x] **Autonomous stock discovery** (Phase 1.2)

### 🚧 Phase 1.2: Additional Strategies (Next)
- [ ] DCA strategy implementation
- [ ] Grid trading strategy
- [ ] Strategy testing and optimization

### 📋 Phase 2: Data Collection (Future)
- [ ] Reddit API integration
- [ ] X.com (Twitter) API integration
- [ ] News API integration
- [ ] Sentiment analysis pipeline
- [ ] Full Sentiment-Momentum strategy

### 📋 Phase 3: Advanced Features (Future)
- [ ] Web dashboard (Streamlit or React)
- [ ] Backtesting framework
- [ ] Machine learning integration
- [ ] Performance analytics

## Troubleshooting

### Bot won't start

```bash
# Check Python version
python --version  # Should be 3.11+

# Verify virtual environment is activated
which python  # Should show venv path

# Check Alpaca connection
python -c "from src.api.alpaca_client import alpaca_client; print(alpaca_client.get_account())"
```

### No trades executing

- Check that it's during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
- Verify strategies are enabled in `.env`
- Check logs for signal generation
- Ensure sufficient buying power in Alpaca account

### Database errors

```bash
# Reinitialize database
rm data/ktrade.db
python scripts/init_db.py
```

## Safety Features

- **Paper Trading Only**: No real money at risk in Phase 1
- **Kill Switch**: Ctrl+C to stop bot immediately
- **Daily Loss Limits**: Automatic trading halt at -3% daily loss
- **Complete Audit Trail**: Every decision logged to database and files
- **Position Limits**: Maximum 10% per position, 80% total exposure

## Project Timeline

- **Week 1**: Foundation ✅ (Complete)
- **Week 2**: Additional strategies and testing (Current)
- **Week 3**: Integration testing and optimization
- **Phase 2+**: Data collection, sentiment analysis, dashboard

## Contributing

This is a personal trading bot project. Not accepting external contributions.

## Disclaimer

⚠️ **IMPORTANT**: This trading bot is for educational and experimental purposes only.

- Trading involves significant financial risk
- Past performance does not guarantee future results
- Only invest money you can afford to lose
- Currently operates in PAPER TRADING mode only
- Author is not liable for any financial losses
- This is not financial advice

## License

Private project - All rights reserved

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Review Alpaca dashboard for account status
3. Verify configuration in `.env`

---

**Status**: Phase 1 Foundation Complete ✅
**Mode**: Paper Trading Only
**Last Updated**: December 13, 2025
