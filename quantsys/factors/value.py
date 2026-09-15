"""Value factors (价值因子) for Chinese A-shares.

Based on proven factors from Zhu Yifeng (2025) 《股票量化投资策略——基于中国A股市场的新发现》
and broker research reports.

Value factors measure how cheap or expensive a stock is relative to its fundamentals.
Higher factor values indicate cheaper stocks (positive expected return direction).
"""

import pandas as pd

from quantsys.factors.base import BaseFactor


class ROEFactor(BaseFactor):
    """Return on Equity (TTM).

    ROE = Net Income (TTM) / Average Shareholders' Equity

    Higher ROE indicates more profitable companies. In A-shares, ROE has been
    shown to have positive predictive power for future returns.
    """

    name = "roe_ttm"
    category = "value"
    frequency = "monthly"
    requires = ["net_income_ttm", "total_equity"]

    def __init__(self, periods: int = 4):
        self.periods = periods

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "roe" in panel.columns:
            return panel["roe"].copy()

        # Try to compute from financial data if available
        if "net_income_ttm" in panel.columns and "total_equity" in panel.columns:
            equity = panel["total_equity"].replace(0, pd.NA)
            return panel["net_income_ttm"] / equity

        return pd.Series(index=panel.index, dtype=float)


class ROAFactor(BaseFactor):
    """Return on Assets (TTM).

    ROA = Net Income (TTM) / Average Total Assets

    Measures management efficiency in using assets to generate earnings.
    """

    name = "roa_ttm"
    category = "value"
    frequency = "monthly"
    requires = ["net_income_ttm", "total_assets"]

    def __init__(self, periods: int = 4):
        self.periods = periods

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "roa" in panel.columns:
            return panel["roa"].copy()

        if "net_income_ttm" in panel.columns and "total_assets" in panel.columns:
            assets = panel["total_assets"].replace(0, pd.NA)
            return panel["net_income_ttm"] / assets

        return pd.Series(index=panel.index, dtype=float)


class EPFactor(BaseFactor):
    """Earnings-to-Price ratio (E/P, 1/PE).

    E/P = 1 / PE_TTM = Earnings per Share / Price

    Higher E/P means higher earnings yield relative to price.
    Classic value factor from Fama-French, adapted for A-shares.
    """

    name = "ep_ttm"
    category = "value"
    frequency = "monthly"
    requires = ["pe_ttm", "close"]

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "pe_ttm" in panel.columns:
            pe = panel["pe_ttm"]
            # Filter extreme PE values
            pe = pe.where((pe > 0) & (pe < 1000))
            return 1.0 / pe

        return pd.Series(index=panel.index, dtype=float)


class BPFactor(BaseFactor):
    """Book-to-Price ratio (B/P, 1/PB).

    B/P = 1 / PB = Book Value per Share / Price

    Higher B/P indicates stocks trading below book value.
    The value premium has been documented in A-shares (Zhu, 2025).
    """

    name = "bp_lr"
    category = "value"
    frequency = "monthly"
    requires = ["pb"]

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "pb" in panel.columns:
            pb = panel["pb"]
            pb = pb.where((pb > 0) & (pb < 100))
            return 1.0 / pb

        return pd.Series(index=panel.index, dtype=float)


class CFPFactor(BaseFactor):
    """Cash Flow to Price ratio.

    CFP = Operating Cash Flow / Market Capitalization

    Higher CFP indicates stronger cash generation relative to price.
    Cash flow is harder to manipulate than earnings, making this
    a more robust value metric in A-shares.
    """

    name = "cashflow_to_mv"
    category = "value"
    frequency = "monthly"
    requires = ["total_mv", "close"]

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        if "ocf_ttm" in panel.columns and "total_mv" in panel.columns:
            mv = panel["total_mv"].replace(0, pd.NA)
            return panel["ocf_ttm"] / mv

        if "net_income_ttm" in panel.columns and "total_mv" in panel.columns:
            # Fallback: use net income as cash flow proxy
            mv = panel["total_mv"].replace(0, pd.NA)
            return panel["net_income_ttm"] / mv

        return pd.Series(index=panel.index, dtype=float)
