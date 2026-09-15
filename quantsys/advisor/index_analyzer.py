"""Index analysis engine for market context and regime detection.

Provides multi-timeframe index metrics, trend analysis, regime
classification, and benchmark return series. Uses cached index_daily
data from data/raw/index_daily/.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quantsys.data.sources.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class IndexSnapshot:
    """Metrics for a single index at one evaluation date."""

    code: str
    name: str = ""
    date: str = ""

    close: float = 0.0
    change_1d: float = 0.0
    change_5d: float = 0.0
    change_20d: float = 0.0
    change_60d: float = 0.0

    volatility_20d: float = 0.0           # Annualized %
    high_52w: float = 0.0
    low_52w: float = 0.0
    position_52w: float = 0.0             # 0-100

    ma20: float = 0.0
    ma60: float = 0.0
    ma120: float = 0.0

    trend: str = "neutral"                # bullish / bearish / neutral
    regime: str = "ranging"               # trending_up / trending_down / ranging / volatile
    volume_ratio: float = 0.0             # Recent volume vs 20d average
    max_drawdown: float = 0.0             # From 52w high (%)


@dataclass
class IndexDashboard:
    """Aggregate dashboard of all tracked indices."""

    date: str
    indices: dict[str, IndexSnapshot] = field(default_factory=dict)
    market_breadth: str = "mixed"                         # broadly_up / mixed / broadly_down
    dominant_regime: str = "ranging"
    volatility_regime: str = "normal"                     # low / normal / high / extreme
    summary: str = ""
    signals: list[str] = field(default_factory=list)


class IndexAnalyzer:
    """Analyze A-share indices for market context and regime detection.

    Loads cached index daily OHLCV data and computes multi-timeframe
    metrics, trend classification, and market regime signals.

    Usage::

        analyzer = IndexAnalyzer()
        dash = analyzer.dashboard("2026-07-15")
        print(dash.summary)
    """

    INDEX_NAMES: dict[str, str] = {
        "000001": "上证指数",
        "000300": "沪深300",
        "000905": "中证500",
        "399006": "创业板指",
        "000688": "科创50",
    }

    DEFAULT_INDICES: list[str] = ["000300", "000905", "000001", "399006", "000688"]

    def __init__(self, cache_dir: str | Path = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "raw"
        self._cache_dir = Path(cache_dir)
        self._cache = CacheManager(self._cache_dir)

    # -- Public API ---------------------------------------------------------

    def snapshot(self, code: str, date: str = None) -> IndexSnapshot | None:
        """Compute single-index metrics at a given date.

        Args:
            code: Index code (e.g. "000300").
            date: Evaluation date. Defaults to today.

        Returns:
            IndexSnapshot or None if no data is available.
        """
        if date is None:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        target_date = pd.Timestamp(date)
        name = self.INDEX_NAMES.get(code, code)

        df = self._cache.get("index_daily", symbol=code)
        if df is None or df.empty:
            logger.warning(f"No cached data for index {code}")
            return None

        df = df.sort_index()
        available = df[df.index <= target_date]
        if available.empty or "close" not in available.columns:
            return None

        closes = available["close"].astype(float)
        if len(closes) < 20:
            return None

        snap = IndexSnapshot(code=code, name=name, date=date)
        current = float(closes.iloc[-1])
        snap.close = current

        # Multi-timeframe returns
        snap.change_1d = self._pct_change(closes, -2) if len(closes) >= 2 else 0
        snap.change_5d = self._pct_change(closes, -6) if len(closes) >= 6 else 0
        snap.change_20d = self._pct_change(closes, -21) if len(closes) >= 21 else 0
        snap.change_60d = self._pct_change(closes, -61) if len(closes) >= 61 else 0

        # Volatility
        rets = closes.pct_change().dropna()
        snap.volatility_20d = float(rets.tail(20).std() * np.sqrt(252) * 100) if len(rets) >= 20 else 0

        # 52-week range
        lookback = min(252, len(closes))
        recent = closes.tail(lookback)
        snap.high_52w = float(recent.max())
        snap.low_52w = float(recent.min())
        rg = snap.high_52w - snap.low_52w
        snap.position_52w = float((current - snap.low_52w) / rg * 100) if rg > 0 else 50
        snap.max_drawdown = float((current / snap.high_52w - 1) * 100) if snap.high_52w > 0 else 0

        # Moving averages
        snap.ma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else current
        snap.ma60 = float(closes.rolling(60).mean().iloc[-1]) if len(closes) >= 60 else current
        snap.ma120 = float(closes.rolling(120).mean().iloc[-1]) if len(closes) >= 120 else current

        # Volume
        if "volume" in available.columns:
            vols = available["volume"].astype(float)
            snap.volume_ratio = float(vols.iloc[-1] / vols.tail(20).mean()) if len(vols) >= 20 and vols.tail(20).mean() > 0 else 1.0

        # Trend classification
        snap.trend = self._classify_trend(current, snap.ma20, snap.ma60, snap.change_20d)

        # Regime detection
        snap.regime = self._detect_regime(current, snap.ma20, snap.ma60,
                                          snap.volatility_20d, snap.change_20d, len(rets))

        return snap

    def dashboard(self, date: str = None, codes: list[str] = None) -> IndexDashboard:
        """Compute aggregate dashboard for all tracked indices.

        Args:
            date: Evaluation date.
            codes: Index codes to include. Defaults to 5 major indices.

        Returns:
            IndexDashboard with all index snapshots and aggregate metrics.
        """
        if date is None:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        if codes is None:
            codes = self.DEFAULT_INDICES

        dash = IndexDashboard(date=date)
        trends = []
        regimes = []
        vols = []
        changes_1d = []

        for code in codes:
            snap = self.snapshot(code, date)
            if snap is None:
                continue
            dash.indices[code] = snap
            trends.append(snap.trend)
            regimes.append(snap.regime)
            vols.append(snap.volatility_20d)
            changes_1d.append(snap.change_1d)

        if not dash.indices:
            dash.summary = "指数数据不可用，请先更新数据"
            return dash

        # Market breadth
        bullish_count = sum(1 for t in trends if t == "bullish")
        bearish_count = sum(1 for t in trends if t == "bearish")
        total = len(trends)
        if bullish_count >= total * 0.6:
            dash.market_breadth = "broadly_up"
        elif bearish_count >= total * 0.6:
            dash.market_breadth = "broadly_down"
        else:
            dash.market_breadth = "mixed"

        # Dominant regime
        if regimes:
            from collections import Counter
            dash.dominant_regime = Counter(regimes).most_common(1)[0][0]

        # Volatility regime
        if vols:
            avg_vol = np.mean(vols)
            if avg_vol < 12:
                dash.volatility_regime = "low"
            elif avg_vol < 22:
                dash.volatility_regime = "normal"
            elif avg_vol < 35:
                dash.volatility_regime = "high"
            else:
                dash.volatility_regime = "extreme"

        # Detect signals
        dash.signals = self._detect_signals(dash)

        # Generate Chinese summary
        dash.summary = self._generate_summary(dash)

        return dash

    def benchmark_returns(self, code: str = "000300", date: str = None,
                          lookback: int = 252) -> pd.Series:
        """Get index daily return series for benchmark calculations.

        Args:
            code: Index code to use as benchmark.
            date: End date.
            lookback: Number of trading days.

        Returns:
            Series of daily returns (indexed by date).
        """
        if date is None:
            from datetime import datetime
            date = datetime.now().strftime("%Y-%m-%d")

        target_date = pd.Timestamp(date)
        df = self._cache.get("index_daily", symbol=code)
        if df is None or df.empty:
            return pd.Series(dtype=float)

        df = df.sort_index()
        available = df[df.index <= target_date]
        if "close" not in available.columns:
            return pd.Series(dtype=float)

        closes = available["close"].astype(float)
        rets = closes.pct_change().dropna().tail(lookback)
        return rets

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _pct_change(series: pd.Series, idx: int) -> float:
        """Percentage change from idx to last."""
        if abs(idx) > len(series):
            return 0.0
        prev = float(series.iloc[idx])
        cur = float(series.iloc[-1])
        return float((cur / prev - 1) * 100) if prev > 0 else 0.0

    @staticmethod
    def _classify_trend(close: float, ma20: float, ma60: float, ret20: float) -> str:
        """Classify price trend."""
        if close > ma20 > ma60 and ret20 > 0:
            return "bullish"
        elif close < ma20 < ma60 and ret20 < 0:
            return "bearish"
        return "neutral"

    def _detect_regime(self, close: float, ma20: float, ma60: float,
                       vol: float, ret20: float, n_days: int) -> str:
        """Detect market regime based on trend and volatility."""
        close_above_ma20 = close > ma20
        close_above_ma60 = close > ma60
        ma_bullish = ma20 > ma60

        if close_above_ma20 and ma_bullish and ret20 > 2:
            return "trending_up"
        elif not close_above_ma20 and not ma_bullish and ret20 < -2:
            return "trending_down"
        elif vol > 30:
            return "volatile"
        return "ranging"

    def _detect_signals(self, dash: IndexDashboard) -> list[str]:
        """Detect cross-index signals."""
        signals = []

        # Divergence: CSI 300 vs CSI 500
        csi300 = dash.indices.get("000300")
        csi500 = dash.indices.get("000905")
        if csi300 and csi500:
            if csi300.trend == "bullish" and csi500.trend == "bearish":
                signals.append("大盘风格占优 (沪深300强于中证500)")
            elif csi300.trend == "bearish" and csi500.trend == "bullish":
                signals.append("小盘风格占优 (中证500强于沪深300)")

        # ChiNext vs CSI 300 divergence = risk-on/off
        cyb = dash.indices.get("399006")
        if csi300 and cyb:
            if cyb.change_20d > 5 and csi300.change_20d < 0:
                signals.append("创业板逆势走强，资金偏向成长")
            elif csi300.change_20d > 3 and cyb.change_20d < -3:
                signals.append("资金偏向防御/价值，创业板走弱")

        # Broad market signal
        if dash.market_breadth == "broadly_up":
            signals.append("市场普涨，整体做多环境")
        elif dash.market_breadth == "broadly_down":
            signals.append("市场普跌，建议降低仓位或配置防御资产")

        return signals

    def _generate_summary(self, dash: IndexDashboard) -> str:
        """Generate a human-readable Chinese market summary."""
        parts = []

        n_bull = sum(1 for s in dash.indices.values() if s.trend == "bullish")
        n_total = len(dash.indices)

        if dash.market_breadth == "broadly_up":
            parts.append(f"市场整体偏强，{n_bull}/{n_total} 指数处于多头趋势")
        elif dash.market_breadth == "broadly_down":
            parts.append(f"市场整体偏弱，仅 {n_bull}/{n_total} 指数处于多头趋势")
        else:
            parts.append(f"市场分化，{n_bull}/{n_total} 指数偏多")

        if dash.dominant_regime == "trending_up":
            parts.append("主导状态为上升趋势，适合趋势跟踪策略")
        elif dash.dominant_regime == "trending_down":
            parts.append("主导状态为下降趋势，注意仓位管理")
        elif dash.dominant_regime == "volatile":
            parts.append("波动加剧，建议降低仓位或使用期权对冲")
        else:
            parts.append("市场以震荡为主，适合网格或区间交易")

        if dash.volatility_regime in ("high", "extreme"):
            parts.append(f"波动率处于{dash.volatility_regime}水平，注意风险管理")

        return "。".join(parts) + "。"
