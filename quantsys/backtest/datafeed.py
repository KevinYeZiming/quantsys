"""Backtrader data feed adapter for Parquet-stored A-share data.

Converts our Parquet-stock data into Backtrader-compatible PandasData feeds
with A-share-specific columns (turnover, amount, etc.).
"""

import backtrader as bt


class AShareDataFeed(bt.feeds.PandasData):
    """Backtrader data feed from Parquet OHLCV data.

    Extends standard PandasData with A-share-specific fields:
    - turnover: daily turnover rate
    - amount: daily transaction amount
    """

    params = (
        ("datetime", None),     # Index is datetime
        ("open", 0),
        ("high", 1),
        ("low", 2),
        ("close", 3),
        ("volume", 4),
        ("openinterest", -1),
    )

    # Extra lines for A-share data
    lines = ("turnover", "amount")

    # Map extra line indices
    params = (
        ("datetime", None),
        ("open", 0),
        ("high", 1),
        ("low", 2),
        ("close", 3),
        ("volume", 4),
        ("openinterest", -1),
        ("turnover", 6),
        ("amount", 5),
    )


def create_datafeed(df, symbol: str = None, **kwargs):
    """Create a Backtrader data feed from a pandas DataFrame.

    Args:
        df: DataFrame with columns [open, high, low, close, volume, amount, turnover]
            indexed by date.
        symbol: Optional stock symbol name for the feed.
        **kwargs: Additional Backtrader data feed params.

    Returns:
        AShareDataFeed instance.
    """
    # Ensure columns are in the expected order
    required = ["open", "high", "low", "close", "volume"]
    if not all(c in df.columns for c in required):
        raise ValueError(f"DataFrame must contain columns: {required}")

    # Fill optional columns with defaults
    df = df.copy()
    if "amount" not in df.columns:
        df["amount"] = 0.0
    if "turnover" not in df.columns:
        df["turnover"] = 0.0

    # Select columns in expected order
    columns = ["open", "high", "low", "close", "volume", "amount", "turnover"]
    df_feed = df[columns]

    params = {
        "dataname": df_feed,
        "name": symbol or "unknown",
        **kwargs,
    }

    return AShareDataFeed(**params)
