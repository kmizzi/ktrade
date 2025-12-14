"""
Configuration settings for the trading bot.
Uses Pydantic BaseSettings for type-safe configuration with .env file support.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Alpaca API Configuration
    alpaca_api_key: str = Field(..., description="Alpaca API key")
    alpaca_secret_key: str = Field(..., description="Alpaca secret key")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca API base URL (paper or live)"
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///data/ktrade.db",
        description="Database connection URL"
    )

    # Bot Configuration
    bot_mode: str = Field(default="paper", description="Bot mode: paper or live")
    log_level: str = Field(default="INFO", description="Logging level")
    environment: str = Field(default="development", description="Environment name")

    # Strategy Configuration
    enable_simple_momentum: bool = Field(default=True)
    enable_dca: bool = Field(default=True)
    enable_grid_trading: bool = Field(default=True)
    enable_sentiment_momentum: bool = Field(default=False)

    # Risk Management
    max_position_size_pct: float = Field(
        default=10.0,
        description="Maximum position size as % of portfolio"
    )
    max_portfolio_exposure_pct: float = Field(
        default=80.0,
        description="Maximum portfolio exposure %"
    )
    daily_loss_limit_pct: float = Field(
        default=3.0,
        description="Daily loss limit as % of portfolio"
    )
    default_stop_loss_pct: float = Field(
        default=5.0,
        description="Default stop loss percentage"
    )

    # Stock Discovery Settings
    enable_dynamic_discovery: bool = Field(
        default=True,
        description="Enable dynamic stock discovery vs static watchlist"
    )
    max_watchlist_size: int = Field(
        default=20,
        description="Maximum number of stocks in dynamic watchlist"
    )
    min_stock_price: float = Field(
        default=5.0,
        description="Minimum stock price for screening"
    )
    min_daily_volume: int = Field(
        default=1000000,
        description="Minimum daily volume for screening"
    )
    top_gainers_count: int = Field(
        default=10,
        description="Number of top gainers to include"
    )
    top_volume_count: int = Field(
        default=10,
        description="Number of high volume stocks to include"
    )

    # Static Watchlist (fallback)
    watchlist_stocks: str = Field(
        default="AAPL,MSFT,GOOGL,AMZN,TSLA",
        description="Comma-separated list of stock symbols"
    )
    watchlist_crypto: str = Field(
        default="BTC/USD,ETH/USD",
        description="Comma-separated list of crypto symbols"
    )

    # Scheduling (in minutes)
    market_data_interval: int = Field(default=5, description="Market data fetch interval")
    strategy_eval_interval: int = Field(default=15, description="Strategy evaluation interval")
    portfolio_sync_interval: int = Field(default=60, description="Portfolio sync interval")

    @field_validator("bot_mode")
    @classmethod
    def validate_bot_mode(cls, v: str) -> str:
        """Validate bot mode is either paper or live"""
        if v not in ["paper", "live"]:
            raise ValueError("bot_mode must be 'paper' or 'live'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper

    @field_validator("max_position_size_pct", "max_portfolio_exposure_pct", "daily_loss_limit_pct", "default_stop_loss_pct")
    @classmethod
    def validate_percentages(cls, v: float) -> float:
        """Validate percentage values"""
        if v < 0 or v > 100:
            raise ValueError("Percentage must be between 0 and 100")
        return v

    def get_watchlist_stocks(self) -> List[str]:
        """Get watchlist stocks as a list"""
        return [s.strip() for s in self.watchlist_stocks.split(",") if s.strip()]

    def get_watchlist_crypto(self) -> List[str]:
        """Get watchlist crypto as a list"""
        return [s.strip() for s in self.watchlist_crypto.split(",") if s.strip()]

    def get_full_watchlist(self) -> List[str]:
        """Get combined watchlist of stocks and crypto"""
        return self.get_watchlist_stocks() + self.get_watchlist_crypto()

    @property
    def is_paper_trading(self) -> bool:
        """Check if bot is in paper trading mode"""
        return self.bot_mode == "paper"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment == "production"


# Global settings instance
settings = Settings()
