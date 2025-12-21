"""
KTrade Dashboard - Main Streamlit Application.
Displays portfolio performance, positions, trades, and metrics.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.dashboard.data_loader import (
    get_portfolio_summary,
    get_positions,
    get_recent_trades,
    get_equity_curve,
    get_backtest_results,
    get_performance_metrics,
    is_market_open,
    get_wsb_trending,
    get_stocktwits_trending,
    get_symbol_sentiment,
    get_market_mood,
    get_news_sentiment,
    get_news_headlines,
    get_market_news_sentiment,
    get_watchlist_news_sentiment,
    get_rate_limit_status,
    get_current_signals,
    get_strategy_performance,
    get_risk_metrics,
    get_watchlist_data,
)

# Page config
st.set_page_config(
    page_title="KTrade Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        border-radius: 10px;
        padding: 15px;
        margin: 5px 0;
    }
    .positive { color: #00c853; }
    .negative { color: #ff5252; }
    .stMetric > div { background-color: transparent; }
</style>
""", unsafe_allow_html=True)


def format_currency(value: float) -> str:
    """Format value as currency."""
    if value >= 0:
        return f"${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_pct(value: float) -> str:
    """Format value as percentage."""
    if value >= 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def color_pct(value: float) -> str:
    """Return color based on positive/negative."""
    return "green" if value >= 0 else "red"


def render_header():
    """Render dashboard header."""
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.title("📈 KTrade Dashboard")

    with col2:
        market_status = "🟢 Market Open" if is_market_open() else "🔴 Market Closed"
        st.markdown(f"### {market_status}")

    with col3:
        st.markdown(f"### 📄 Paper Trading")
        st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")


def render_portfolio_summary():
    """Render portfolio summary metrics."""
    summary = get_portfolio_summary()

    if not summary:
        st.warning("No portfolio data available. Make sure the bot is running.")
        return

    st.subheader("Portfolio Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Portfolio Value",
            format_currency(summary['total_value']),
            format_pct(summary['total_return_pct'])
        )

    with col2:
        st.metric(
            "Today's P&L",
            format_currency(summary['daily_pnl']),
            format_pct(summary['daily_pnl_pct'])
        )

    with col3:
        st.metric(
            "Cash",
            format_currency(summary['cash']),
        )

    with col4:
        st.metric(
            "Positions Value",
            format_currency(summary['positions_value']),
        )

    with col5:
        st.metric(
            "Open Positions",
            summary['num_positions'],
        )


def render_equity_curve():
    """Render equity curve chart."""
    st.subheader("Equity Curve")

    df = get_equity_curve()

    if df.empty:
        st.info("No equity data available yet. Run a backtest or start trading to see data.")
        return

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add equity line
    fig.add_trace(
        go.Scatter(
            x=df['date'],
            y=df['total_value'],
            name="Portfolio Value",
            line=dict(color='#00c853', width=2),
            fill='tozeroy',
            fillcolor='rgba(0, 200, 83, 0.1)'
        ),
        secondary_y=False
    )

    # Add daily return bars if available
    if 'daily_return_pct' in df.columns:
        colors = ['#00c853' if x >= 0 else '#ff5252' for x in df['daily_return_pct']]
        fig.add_trace(
            go.Bar(
                x=df['date'],
                y=df['daily_return_pct'],
                name="Daily Return %",
                marker_color=colors,
                opacity=0.5
            ),
            secondary_y=True
        )

    fig.update_layout(
        height=400,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(title_text="Portfolio Value ($)", secondary_y=False, showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(title_text="Daily Return (%)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)


def render_positions():
    """Render current positions table."""
    st.subheader("Current Positions")

    positions = get_positions()

    if not positions:
        st.info("No open positions")
        return

    # Convert to DataFrame for display
    df = pd.DataFrame(positions)

    # Style the dataframe
    def style_pnl(val):
        if isinstance(val, (int, float)):
            color = 'green' if val >= 0 else 'red'
            return f'color: {color}'
        return ''

    # Format columns
    if 'unrealized_pnl' in df.columns:
        df['P&L'] = df['unrealized_pnl'].apply(lambda x: format_currency(x))
        df['P&L %'] = df['unrealized_pnl_pct'].apply(lambda x: format_pct(x))

    if 'current_price' in df.columns:
        df['Current Price'] = df['current_price'].apply(lambda x: f"${x:.2f}")

    if 'avg_entry_price' in df.columns:
        df['Entry Price'] = df['avg_entry_price'].apply(lambda x: f"${x:.2f}")

    if 'market_value' in df.columns:
        df['Market Value'] = df['market_value'].apply(lambda x: format_currency(x))

    # Select and rename columns for display
    display_cols = ['symbol', 'quantity', 'Entry Price', 'Current Price', 'Market Value', 'P&L', 'P&L %']
    display_cols = [c for c in display_cols if c in df.columns]

    if display_cols:
        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True
        )


def render_recent_trades():
    """Render recent trades table."""
    st.subheader("Recent Trades")

    trades = get_recent_trades(limit=20)

    if not trades:
        st.info("No trades yet")
        return

    df = pd.DataFrame(trades)

    # Format columns with friendly date/time
    if 'timestamp' in df.columns:
        df['Date'] = pd.to_datetime(df['timestamp']).dt.strftime('%b %d, %Y %-I:%M %p')
    elif 'date' in df.columns:
        df['Date'] = pd.to_datetime(df['date']).dt.strftime('%b %d, %Y %-I:%M %p')

    if 'price' in df.columns:
        df['Price'] = df['price'].apply(lambda x: f"${x:.2f}")

    if 'value' in df.columns:
        df['Value'] = df['value'].apply(lambda x: format_currency(x))
    elif 'total_value' in df.columns:
        df['Value'] = df['total_value'].apply(lambda x: format_currency(x))

    # Color code buy/sell
    if 'side' in df.columns:
        df['Side'] = df['side'].apply(lambda x: f"🟢 {x.upper()}" if x.lower() == 'buy' else f"🔴 {x.upper()}")

    # Select columns for display
    display_cols = ['Date', 'symbol', 'Side', 'quantity', 'Price', 'Value', 'reason']
    display_cols = [c for c in display_cols if c in df.columns]

    if display_cols:
        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True
        )


def render_metrics():
    """Render performance metrics."""
    st.subheader("Performance Metrics")

    metrics = get_performance_metrics()

    if not metrics:
        st.info("No performance metrics available. Run a backtest to see metrics.")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Return", format_pct(metrics.get('total_return_pct', 0)))
        st.metric("Win Rate", f"{metrics.get('win_rate_pct', 0):.1f}%")

    with col2:
        st.metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
        st.metric("Sortino Ratio", f"{metrics.get('sortino_ratio', 0):.2f}")

    with col3:
        st.metric("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f}%")
        st.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")

    with col4:
        st.metric("Total Trades", metrics.get('total_trades', 0))
        st.metric("Avg Trade", format_pct(metrics.get('avg_trade_pct', 0)))


def render_sentiment():
    """Render sentiment analysis section."""
    st.subheader("Market Sentiment")

    # Show rate limit status
    rate_status = get_rate_limit_status()
    if rate_status and 'requests_remaining' in rate_status:
        remaining = rate_status['requests_remaining']
        made = rate_status['requests_made']
        limit = rate_status['daily_limit']

        # Color based on remaining
        if remaining > 15:
            status_color = "🟢"
        elif remaining > 5:
            status_color = "🟡"
        else:
            status_color = "🔴"

        st.caption(
            f"{status_color} API Quota: {remaining}/{limit} remaining today "
            f"(refreshes ~every {rate_status.get('recommended_interval_minutes', 60)} min)"
        )

    # Market mood from news - use session state to avoid refetching on every rerun
    # Only fetch on initial load, not when buttons are clicked
    if 'market_news_cache' not in st.session_state:
        st.session_state.market_news_cache = get_market_news_sentiment()

    market_news = st.session_state.market_news_cache
    if market_news and 'market_sentiment' in market_news:
        score = market_news['market_sentiment']
        if score > 0.15:
            mood_emoji, mood_text = "🟢", "Bullish"
        elif score < -0.15:
            mood_emoji, mood_text = "🔴", "Bearish"
        else:
            mood_emoji, mood_text = "🟡", "Neutral"
        st.markdown(f"### {mood_emoji} News Sentiment: **{mood_text}** ({score:+.2f})")
        st.caption(f"Based on {market_news.get('article_count', 0)} recent market articles")
    else:
        st.markdown("### 📰 News Sentiment")

    st.divider()

    # Two columns - News lookup and Watchlist sentiment
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔍 Symbol News Lookup")

        # Initialize session state for symbol lookup
        if 'symbol_sentiment_cache' not in st.session_state:
            st.session_state.symbol_sentiment_cache = None
            st.session_state.symbol_sentiment_symbol = None

        # Symbol input
        lookup_symbol = st.text_input(
            "Enter symbol",
            value="AAPL",
            max_chars=5,
            key="news_lookup"
        ).upper()

        if st.button("Get News Sentiment", key="lookup_btn"):
            with st.spinner(f"Fetching news for {lookup_symbol}..."):
                sentiment = get_news_sentiment(lookup_symbol)
                st.session_state.symbol_sentiment_cache = sentiment
                st.session_state.symbol_sentiment_symbol = lookup_symbol

        # Display cached result
        if st.session_state.symbol_sentiment_cache and st.session_state.symbol_sentiment_symbol:
            sentiment = st.session_state.symbol_sentiment_cache
            symbol = st.session_state.symbol_sentiment_symbol

            if sentiment and 'error' not in sentiment:
                score = sentiment.get('sentiment_score', 0)
                label = sentiment.get('sentiment_label', 'Neutral')

                # Display sentiment score with color
                if score > 0.15:
                    st.success(f"**{symbol}**: {label} ({score:+.3f})")
                elif score < -0.15:
                    st.error(f"**{symbol}**: {label} ({score:+.3f})")
                else:
                    st.warning(f"**{symbol}**: {label} ({score:+.3f})")

                st.caption(f"Based on {sentiment.get('article_count', 0)} articles")

                # Show headlines
                articles = sentiment.get('articles', [])
                if articles:
                    st.markdown("**Recent Headlines:**")
                    for article in articles[:5]:
                        title = article.get('title', 'No title')[:80]
                        art_score = article.get('sentiment_score', 0)
                        emoji = "🟢" if art_score > 0.1 else "🔴" if art_score < -0.1 else "🟡"
                        st.markdown(f"- {emoji} {title}...")
            else:
                error_msg = sentiment.get('error', 'Unknown error') if sentiment else 'No data'
                st.error(f"Could not fetch news for {symbol}: {error_msg}")

    with col2:
        st.markdown("#### 📊 Watchlist Sentiment")

        # Use cached watchlist sentiment, only fetch on button click
        if 'watchlist_sentiment_cache' not in st.session_state:
            st.session_state.watchlist_sentiment_cache = None

        watchlist_sentiment = st.session_state.watchlist_sentiment_cache

        if watchlist_sentiment:
            df = pd.DataFrame(watchlist_sentiment)

            # Add emoji indicator
            df['Mood'] = df['sentiment_score'].apply(
                lambda x: "🟢" if x > 0.15 else "🔴" if x < -0.15 else "🟡"
            )
            df['Score'] = df['sentiment_score'].apply(lambda x: f"{x:+.2f}")
            df['Articles'] = df['article_count']

            st.dataframe(
                df[['symbol', 'Mood', 'Score', 'Articles']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Click to load watchlist sentiment")

            if st.button("Load Sentiment", key="load_watchlist"):
                with st.spinner("Fetching watchlist sentiment..."):
                    st.session_state.watchlist_sentiment_cache = get_watchlist_news_sentiment()
                st.rerun()

    st.divider()

    # Collapsed section for social sentiment (WSB/StockTwits)
    with st.expander("📱 Social Sentiment (Limited Availability)"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**WSB Trending**")
            wsb_trending = get_wsb_trending()
            if wsb_trending:
                wsb_df = pd.DataFrame(wsb_trending)
                st.dataframe(wsb_df[['symbol', 'mentions']].head(10), hide_index=True)
            else:
                st.caption("Requires Quiver Quant subscription")

        with col2:
            st.markdown("**StockTwits Trending**")
            st_trending = get_stocktwits_trending()
            if st_trending:
                st_df = pd.DataFrame(st_trending)
                st.dataframe(st_df[['symbol']].head(10), hide_index=True)
            else:
                st.caption("API temporarily unavailable")


def render_trading_signals():
    """Render current trading signals panel."""
    st.subheader("📡 Trading Signals")

    # Use session state to cache signals
    if 'signals_cache' not in st.session_state:
        st.session_state.signals_cache = None

    col1, col2 = st.columns([3, 1])

    with col2:
        if st.button("🔄 Refresh Signals", key="refresh_signals"):
            with st.spinner("Generating signals..."):
                st.session_state.signals_cache = get_current_signals()
            st.rerun()

    with col1:
        if st.session_state.signals_cache is None:
            st.info("Click 'Refresh Signals' to generate current trading signals")
            return

    signals = st.session_state.signals_cache

    if not signals:
        st.info("No trading signals generated. Market may be closed or no opportunities detected.")
        return

    # Group signals by type
    buy_signals = [s for s in signals if s['signal_type'] == 'buy']
    sell_signals = [s for s in signals if s['signal_type'] == 'sell']

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🟢 BUY Signals")
        if buy_signals:
            for sig in buy_signals[:5]:
                confidence_pct = sig['confidence'] * 100
                emoji = "🔥" if confidence_pct >= 80 else "✅" if confidence_pct >= 70 else "📈"
                st.markdown(
                    f"{emoji} **{sig['symbol']}** - {confidence_pct:.0f}% confidence\n\n"
                    f"   *{sig['strategy']}*: {sig['notes'][:60]}..."
                )
        else:
            st.caption("No buy signals")

    with col2:
        st.markdown("#### 🔴 SELL Signals")
        if sell_signals:
            for sig in sell_signals[:5]:
                confidence_pct = sig['confidence'] * 100
                emoji = "⚠️" if confidence_pct >= 80 else "📉"
                st.markdown(
                    f"{emoji} **{sig['symbol']}** - {confidence_pct:.0f}% confidence\n\n"
                    f"   *{sig['strategy']}*: {sig['notes'][:60]}..."
                )
        else:
            st.caption("No sell signals")


def render_strategy_performance():
    """Render strategy performance breakdown."""
    st.subheader("📊 Strategy Performance")

    perf = get_strategy_performance()

    if not perf:
        st.info("No strategy performance data available. Execute some trades first.")
        return

    # Create columns for each strategy
    cols = st.columns(len(perf))

    strategy_names = {
        'simple_momentum': '📈 Momentum',
        'news_momentum': '📰 News',
        'dca': '💰 DCA',
        'grid': '📐 Grid',
        'other': '❓ Other',
    }

    for idx, (strat_name, stats) in enumerate(perf.items()):
        with cols[idx]:
            display_name = strategy_names.get(strat_name, strat_name)
            st.markdown(f"**{display_name}**")

            st.metric("Trades", stats['trades'])
            st.caption(f"📥 {stats['buys']} buys / 📤 {stats['sells']} sells")
            st.caption(f"🏷️ {stats['symbols_traded']} symbols")
            st.caption(f"💵 ${stats['total_value']:,.0f} volume")

            # Show percentage as progress bar
            st.progress(min(1.0, stats['pct_of_trades'] / 100))
            st.caption(f"{stats['pct_of_trades']:.1f}% of trades")


def render_risk_monitor():
    """Render risk monitoring section."""
    st.subheader("⚠️ Risk Monitor")

    risk = get_risk_metrics()

    if not risk:
        st.info("No risk data available.")
        return

    # Create three columns for different risk categories
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### Daily Loss Limit")

        # Progress bar for daily loss
        used_pct = risk['daily_loss_used_pct']
        limit_pct = risk['daily_loss_limit_pct']
        progress = min(1.0, used_pct / limit_pct) if limit_pct > 0 else 0

        if risk['daily_loss_critical']:
            st.error(f"🛑 LIMIT REACHED: {used_pct:.2f}% / {limit_pct:.1f}%")
        elif risk['daily_loss_warning']:
            st.warning(f"⚠️ Warning: {used_pct:.2f}% / {limit_pct:.1f}%")
        else:
            st.success(f"✅ OK: {used_pct:.2f}% / {limit_pct:.1f}%")

        st.progress(progress)
        st.caption(f"Today's P&L: {format_currency(risk['daily_pnl'])} ({format_pct(risk['daily_pnl_pct'])})")

    with col2:
        st.markdown("#### Portfolio Exposure")

        exposure = risk['exposure_pct']
        max_exp = risk['max_exposure_pct']
        exp_progress = min(1.0, exposure / max_exp) if max_exp > 0 else 0

        if risk['exposure_warning']:
            st.warning(f"⚠️ Near max: {exposure:.1f}% / {max_exp:.1f}%")
        else:
            st.success(f"✅ OK: {exposure:.1f}% / {max_exp:.1f}%")

        st.progress(exp_progress)
        st.caption(f"Cash: {format_currency(risk['cash'])}")
        st.caption(f"Invested: {format_currency(risk['positions_value'])}")

    with col3:
        st.markdown("#### Position Concentration")

        largest = risk['largest_position_pct']
        max_size = risk['max_position_size_pct']
        conc_progress = min(1.0, largest / max_size) if max_size > 0 else 0

        if risk['concentration_warning']:
            st.warning(f"⚠️ {risk['largest_position_symbol']}: {largest:.1f}% / {max_size:.1f}%")
        else:
            if risk['largest_position_symbol']:
                st.success(f"✅ {risk['largest_position_symbol']}: {largest:.1f}% / {max_size:.1f}%")
            else:
                st.info("No positions")

        st.progress(conc_progress)
        st.caption(f"{risk['num_positions']} open positions")


def render_live_watchlist():
    """Render live watchlist with prices and signals."""
    st.subheader("👁️ Live Watchlist")

    # Use session state to cache watchlist data
    if 'watchlist_cache' not in st.session_state:
        st.session_state.watchlist_cache = None

    col1, col2 = st.columns([3, 1])

    with col2:
        if st.button("🔄 Refresh Watchlist", key="refresh_watchlist"):
            with st.spinner("Fetching market data..."):
                st.session_state.watchlist_cache = get_watchlist_data()
            st.rerun()

    with col1:
        if st.session_state.watchlist_cache is None:
            st.info("Click 'Refresh Watchlist' to load current prices and signals")
            return

    watchlist = st.session_state.watchlist_cache

    if not watchlist:
        st.info("No watchlist data available. Check your watchlist configuration.")
        return

    # Convert to DataFrame for display
    df = pd.DataFrame(watchlist)

    # Format columns
    df['Price'] = df['price'].apply(lambda x: f"${x:.2f}")
    df['Change'] = df['change_pct'].apply(lambda x: f"{x:+.2f}%")
    df['RSI'] = df['rsi'].apply(lambda x: f"{x:.1f}" if x else "N/A")
    df['vs SMA'] = df['vs_sma'].apply(lambda x: f"{x:+.1f}%")
    df['Vol Ratio'] = df['volume_ratio'].apply(lambda x: f"{x:.1f}x")

    # Signal with emoji
    def format_signal(row):
        sig = row['signal']
        strength = row['signal_strength']
        if sig == 'BUY':
            return f"🟢 BUY ({strength:.0%})"
        elif sig == 'SELL':
            return f"🔴 SELL ({strength:.0%})"
        return "⚪ HOLD"

    df['Signal'] = df.apply(format_signal, axis=1)

    # Owned indicator
    df['Owned'] = df['owned'].apply(lambda x: "✅" if x else "")

    # Select columns for display
    display_cols = ['symbol', 'Price', 'Change', 'RSI', 'vs SMA', 'Vol Ratio', 'Signal', 'Owned']

    # Style the dataframe
    st.dataframe(
        df[display_cols].rename(columns={'symbol': 'Symbol'}),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Symbol': st.column_config.TextColumn('Symbol', width='small'),
            'Price': st.column_config.TextColumn('Price', width='small'),
            'Change': st.column_config.TextColumn('Change', width='small'),
            'RSI': st.column_config.TextColumn('RSI', width='small'),
            'vs SMA': st.column_config.TextColumn('vs SMA', width='small'),
            'Vol Ratio': st.column_config.TextColumn('Vol', width='small'),
            'Signal': st.column_config.TextColumn('Signal', width='medium'),
            'Owned': st.column_config.TextColumn('', width='small'),
        }
    )


def render_backtest_selector():
    """Render backtest results selector."""
    st.subheader("Backtest Results")

    backtest_files = get_backtest_results()

    if not backtest_files:
        st.info("No backtest results found. Run `python scripts/run_backtest.py` to generate results.")
        return

    selected = st.selectbox(
        "Select backtest",
        options=backtest_files,
        format_func=lambda x: x.stem
    )

    if selected:
        df = pd.read_csv(selected)

        # Show equity curve from backtest
        if 'total_value' in df.columns:
            fig = px.line(
                df,
                x='date',
                y='total_value',
                title='Backtest Equity Curve'
            )
            fig.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Show summary stats
        if 'total_value' in df.columns and len(df) > 0:
            start_val = df['total_value'].iloc[0]
            end_val = df['total_value'].iloc[-1]
            total_return = ((end_val - start_val) / start_val) * 100

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Start Value", format_currency(start_val))
            with col2:
                st.metric("End Value", format_currency(end_val))
            with col3:
                st.metric("Return", format_pct(total_return))


def render_sidebar():
    """Render sidebar with controls."""
    with st.sidebar:
        st.header("Controls")

        # Auto-refresh toggle
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
        if auto_refresh:
            st.rerun()

        st.divider()

        # Data source
        st.subheader("Data Source")
        data_source = st.radio(
            "View data from:",
            ["Live/Paper Trading", "Backtest Results"],
            index=0
        )

        st.divider()

        # Quick actions
        st.subheader("Quick Actions")

        if st.button("🔄 Refresh Data"):
            # Clear all caches to force refresh
            caches_to_clear = [
                'market_news_cache',
                'watchlist_sentiment_cache',
                'symbol_sentiment_cache',
                'symbol_sentiment_symbol',
                'signals_cache',
                'watchlist_cache',
            ]
            for cache_key in caches_to_clear:
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
            st.rerun()

        st.divider()

        # Info
        st.caption("KTrade v1.0")
        st.caption("Paper Trading Mode")

        return data_source


def main():
    """Main dashboard entry point."""
    # Render sidebar
    data_source = render_sidebar()

    # Header
    render_header()

    st.divider()

    # Main content based on data source
    if data_source == "Live/Paper Trading":
        # Portfolio summary
        render_portfolio_summary()

        st.divider()

        # Risk Monitor - important to show early
        render_risk_monitor()

        st.divider()

        # Equity curve and metrics side by side
        col1, col2 = st.columns([2, 1])

        with col1:
            render_equity_curve()

        with col2:
            render_metrics()

        st.divider()

        # Trading Signals and Live Watchlist
        col1, col2 = st.columns(2)

        with col1:
            render_trading_signals()

        with col2:
            render_live_watchlist()

        st.divider()

        # Strategy Performance breakdown
        render_strategy_performance()

        st.divider()

        # Positions and trades
        col1, col2 = st.columns(2)

        with col1:
            render_positions()

        with col2:
            render_recent_trades()

        st.divider()

        # Sentiment section
        render_sentiment()

    else:
        # Backtest view
        render_backtest_selector()

        # Load trades from most recent backtest
        backtest_files = get_backtest_results()
        if backtest_files:
            trades_file = str(backtest_files[0]).replace('equity', 'trades')
            if Path(trades_file).exists():
                st.subheader("Backtest Trades")
                trades_df = pd.read_csv(trades_file)
                st.dataframe(trades_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
