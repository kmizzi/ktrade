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

    # Market mood from news
    market_news = get_market_news_sentiment()
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

                if sentiment and 'error' not in sentiment:
                    score = sentiment.get('sentiment_score', 0)
                    label = sentiment.get('sentiment_label', 'Neutral')

                    # Display sentiment score with color
                    if score > 0.15:
                        st.success(f"**{lookup_symbol}**: {label} ({score:+.3f})")
                    elif score < -0.15:
                        st.error(f"**{lookup_symbol}**: {label} ({score:+.3f})")
                    else:
                        st.warning(f"**{lookup_symbol}**: {label} ({score:+.3f})")

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
                    st.error(f"Could not fetch news for {lookup_symbol}")

    with col2:
        st.markdown("#### 📊 Watchlist Sentiment")

        watchlist_sentiment = get_watchlist_news_sentiment()

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
            st.info("Click refresh to load watchlist sentiment")

            if st.button("Load Sentiment", key="load_watchlist"):
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

        # Equity curve and positions side by side
        col1, col2 = st.columns([2, 1])

        with col1:
            render_equity_curve()

        with col2:
            render_metrics()

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
