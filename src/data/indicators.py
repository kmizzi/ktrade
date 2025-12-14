"""
Technical indicators calculation using pandas-ta.
Provides common indicators for trading strategies.
"""

from typing import List, Dict, Any
import pandas as pd
import pandas_ta as ta
import structlog

logger = structlog.get_logger(__name__)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).

    Args:
        prices: Series of closing prices
        period: RSI period (default: 14)

    Returns:
        Series of RSI values
    """
    return ta.rsi(prices, length=period)


def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Simple Moving Average (SMA).

    Args:
        prices: Series of closing prices
        period: SMA period (default: 20)

    Returns:
        Series of SMA values
    """
    return ta.sma(prices, length=period)


def calculate_ema(prices: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA).

    Args:
        prices: Series of closing prices
        period: EMA period (default: 20)

    Returns:
        Series of EMA values
    """
    return ta.ema(prices, length=period)


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        prices: Series of closing prices
        fast: Fast period (default: 12)
        slow: Slow period (default: 26)
        signal: Signal period (default: 9)

    Returns:
        DataFrame with MACD, signal, and histogram columns
    """
    return ta.macd(prices, fast=fast, slow=slow, signal=signal)


def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std: float = 2.0) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.

    Args:
        prices: Series of closing prices
        period: Period (default: 20)
        std: Standard deviation multiplier (default: 2.0)

    Returns:
        DataFrame with upper, middle, and lower bands
    """
    return ta.bbands(prices, length=period, std=std)


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate Volume Weighted Average Price (VWAP).

    Args:
        df: DataFrame with 'high', 'low', 'close', 'volume' columns

    Returns:
        Series of VWAP values
    """
    return ta.vwap(df['high'], df['low'], df['close'], df['volume'])


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR).

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        period: ATR period (default: 14)

    Returns:
        Series of ATR values
    """
    return ta.atr(df['high'], df['low'], df['close'], length=period)


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    """
    Calculate Stochastic Oscillator.

    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        k_period: %K period (default: 14)
        d_period: %D period (default: 3)

    Returns:
        DataFrame with %K and %D values
    """
    return ta.stoch(df['high'], df['low'], df['close'], k=k_period, d=d_period)


def calculate_all_indicators(bars: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Calculate all common indicators for a symbol.

    Args:
        bars: List of bar data dicts with OHLCV data

    Returns:
        DataFrame with all indicators calculated
    """
    try:
        # Convert to DataFrame
        df = pd.DataFrame(bars)

        if df.empty:
            logger.warning("empty_bars_data")
            return df

        # Calculate indicators
        df['rsi'] = calculate_rsi(df['close'])
        df['sma_20'] = calculate_sma(df['close'], 20)
        df['sma_50'] = calculate_sma(df['close'], 50)
        df['ema_12'] = calculate_ema(df['close'], 12)
        df['ema_26'] = calculate_ema(df['close'], 26)

        # MACD
        macd = calculate_macd(df['close'])
        if macd is not None and not macd.empty:
            df = pd.concat([df, macd], axis=1)

        # Bollinger Bands
        bbands = calculate_bollinger_bands(df['close'])
        if bbands is not None and not bbands.empty:
            df = pd.concat([df, bbands], axis=1)

        # ATR
        df['atr'] = calculate_atr(df)

        # VWAP (if we have volume)
        if 'volume' in df.columns:
            df['vwap'] = calculate_vwap(df)

        logger.debug(
            "indicators_calculated",
            rows=len(df),
            columns=list(df.columns)
        )

        return df

    except Exception as e:
        logger.error("failed_to_calculate_indicators", error=str(e))
        return pd.DataFrame(bars)


def get_latest_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Get the latest indicator values from a DataFrame.

    Args:
        df: DataFrame with calculated indicators

    Returns:
        Dict of latest indicator values
    """
    if df.empty:
        return {}

    latest = df.iloc[-1]
    return {
        "close": float(latest.get('close', 0)),
        "rsi": float(latest.get('rsi', 0)) if pd.notna(latest.get('rsi')) else None,
        "sma_20": float(latest.get('sma_20', 0)) if pd.notna(latest.get('sma_20')) else None,
        "sma_50": float(latest.get('sma_50', 0)) if pd.notna(latest.get('sma_50')) else None,
        "ema_12": float(latest.get('ema_12', 0)) if pd.notna(latest.get('ema_12')) else None,
        "ema_26": float(latest.get('ema_26', 0)) if pd.notna(latest.get('ema_26')) else None,
        "macd": float(latest.get('MACD_12_26_9', 0)) if pd.notna(latest.get('MACD_12_26_9')) else None,
        "macd_signal": float(latest.get('MACDs_12_26_9', 0)) if pd.notna(latest.get('MACDs_12_26_9')) else None,
        "macd_hist": float(latest.get('MACDh_12_26_9', 0)) if pd.notna(latest.get('MACDh_12_26_9')) else None,
        "bb_upper": float(latest.get('BBU_20_2.0', 0)) if pd.notna(latest.get('BBU_20_2.0')) else None,
        "bb_middle": float(latest.get('BBM_20_2.0', 0)) if pd.notna(latest.get('BBM_20_2.0')) else None,
        "bb_lower": float(latest.get('BBL_20_2.0', 0)) if pd.notna(latest.get('BBL_20_2.0')) else None,
        "atr": float(latest.get('atr', 0)) if pd.notna(latest.get('atr')) else None,
        "vwap": float(latest.get('vwap', 0)) if pd.notna(latest.get('vwap')) else None,
    }
