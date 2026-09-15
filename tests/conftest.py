"""Shared fixtures for tests."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing.

    Returns:
        DataFrame with 100 days of simulated stock data.
    """
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    close = 10 + np.cumsum(np.random.randn(100) * 0.2)
    close = np.maximum(close, 1.0)

    df = pd.DataFrame(
        {
            "open": close * (1 + np.random.randn(100) * 0.005),
            "high": close * (1 + np.abs(np.random.randn(100) * 0.01)),
            "low": close * (1 - np.abs(np.random.randn(100) * 0.01)),
            "close": close,
            "volume": np.random.randint(1000000, 10000000, 100),
            "amount": np.random.randint(10000000, 100000000, 100),
            "turnover": np.random.rand(100) * 5,
        },
        index=dates,
    )
    # Ensure high >= close >= low
    df["high"] = df[["high", "close"]].max(axis=1)
    df["high"] = df[["high", "low"]].max(axis=1) + 0.01
    df["low"] = df[["low", "close"]].min(axis=1)
    return df


@pytest.fixture
def sample_factor_panel():
    """Generate a panel of stocks with factor values.

    Returns:
        DataFrame with MultiIndex (date, symbol) and factor columns.
    """
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=20, freq="B")
    symbols = [f"00000{i}" for i in range(1, 11)] + [f"60000{i}" for i in range(1, 11)]

    rows = []
    for date in dates:
        for sym in symbols:
            rows.append(
                {
                    "date": date,
                    "symbol": sym,
                    "roe_ttm": np.random.randn() * 0.05 + 0.10,
                    "momentum_60d": np.random.randn() * 0.1,
                    "turnover_20d": np.random.exponential(2) / 100,
                    "close": np.random.lognormal(2, 1),
                    "total_mv": np.random.lognormal(22, 2),
                    "industry": np.random.choice(["银行", "医药", "科技", "消费", "制造"]),
                    "forward_return_20d": np.random.randn() * 0.05,
                }
            )

    df = pd.DataFrame(rows)
    return df.set_index(["date", "symbol"])


@pytest.fixture
def sample_returns():
    """Generate sample daily return series."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=252, freq="B")
    returns = pd.Series(np.random.randn(252) * 0.02, index=dates, name="return")
    return returns
