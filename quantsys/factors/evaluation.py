"""Factor evaluation framework (因子有效性评估).

Implements the mainstream single-factor test methodology used by
broker quant research teams (东方证券/光大证券 factor test standards)
and the Alphalens-style analysis pipeline:

    1. IC / RankIC      — daily cross-sectional correlation between
                          factor value and forward return (Pearson & Spearman)
    2. ICIR             — mean(IC) / std(IC), annualized t-statistic
    3. IC decay         — IC at multiple forward horizons (1/3/5/10/20d)
                          to measure factor half-life
    4. Quantile returns — decile portfolio forward returns, long-short
                          spread and monotonicity (分层回测)
    5. Turnover         — top-quantile membership churn between dates
    6. Factor correlation — mean daily cross-sectional rank correlation
                          matrix (redundancy diagnosis)

Usage::

    evaluator = FactorEvaluator()
    summary, details = evaluator.evaluate_all(factor_df, close)
    print(summary)
    report_md = evaluator.to_markdown(summary, details)

``factor_df``: DataFrame with MultiIndex (date, symbol), one column per factor.
``close``: Series with the same MultiIndex (or DataFrame with a 'close' column).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sps

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class FactorStats:
    """Summary statistics for a single factor."""

    factor: str
    n_days: int = 0
    ic_mean: float = np.nan          # Pearson IC mean
    ic_std: float = np.nan
    icir: float = np.nan             # ic_mean / ic_std
    ic_tstat: float = np.nan         # annualized t-stat of IC series
    ic_positive_ratio: float = np.nan
    rank_ic_mean: float = np.nan     # Spearman RankIC mean
    rank_ic_std: float = np.nan
    rank_icir: float = np.nan
    rank_ic_positive_ratio: float = np.nan
    # Decay: {horizon: rank_ic_mean}
    decay: dict = field(default_factory=dict)
    # Quantile analysis at primary horizon
    long_short_ann: float = np.nan   # annualized Q_top - Q_bottom spread
    monotonicity: float = np.nan     # spearman(quantile_idx, mean_return)
    turnover: float = np.nan         # top-quantile membership churn (0-1)
    coverage: float = np.nan         # non-NaN factor ratio
    grade: str = "D"                 # A/B/C/D composite grade
    score: float = 0.0               # composite acceptance score 0-100


class FactorEvaluator:
    """Single-factor evaluation engine.

    Args:
        horizons: Forward return horizons (trading days) for IC decay.
        n_quantiles: Number of quantile buckets for layered backtest.
        min_cross_section: Minimum stocks per day for a valid IC observation.
        periods_per_year: Trading days per year (A-share: 252).
        primary_horizon: Horizon used for quantile/turnover analysis.
    """

    def __init__(
        self,
        horizons: tuple[int, ...] = (1, 3, 5, 10, 20),
        n_quantiles: int = 10,
        min_cross_section: int = 30,
        periods_per_year: int = 252,
        primary_horizon: int = 5,
    ):
        self.horizons = tuple(horizons)
        self.n_quantiles = n_quantiles
        self.min_cross_section = min_cross_section
        self.ppy = periods_per_year
        self.primary_horizon = primary_horizon

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_all(
        self,
        factor_df: pd.DataFrame,
        close: pd.Series | pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict]:
        """Evaluate every factor column against forward returns.

        Args:
            factor_df: MultiIndex (date, symbol) DataFrame of factor values.
            close: Close price with matching MultiIndex (Series or DataFrame
                   containing a 'close' column).

        Returns:
            (summary DataFrame, details dict keyed by factor name with
            daily IC series, quantile return table, and correlation matrix
            stored under the special key '_correlation').
        """
        close_s = self._extract_close(close)
        if isinstance(factor_df, pd.Series):
            factor_df = factor_df.to_frame()

        fwd = self.forward_returns(close_s, self.horizons)
        corr_matrix = self.correlation_matrix(factor_df)

        summary_rows: list[dict] = []
        details: dict = {}

        for factor in factor_df.columns:
            series = factor_df[factor]
            try:
                stats = self.evaluate_factor(series, fwd)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Failed to evaluate factor {factor}: {e}")
                continue

            stats.coverage = float(series.notna().mean())
            self._grade(stats)

            summary_rows.append({
                "factor": factor,
                "n_days": stats.n_days,
                "ic_mean": stats.ic_mean,
                "ic_std": stats.ic_std,
                "icir": stats.icir,
                "ic_tstat": stats.ic_tstat,
                "ic_pos_ratio": stats.ic_positive_ratio,
                "rank_ic_mean": stats.rank_ic_mean,
                "rank_ic_std": stats.rank_ic_std,
                "rank_icir": stats.rank_icir,
                "rank_ic_pos_ratio": stats.rank_ic_positive_ratio,
                "long_short_ann": stats.long_short_ann,
                "monotonicity": stats.monotonicity,
                "turnover": stats.turnover,
                "coverage": stats.coverage,
                "grade": stats.grade,
                "score": stats.score,
                **{f"rank_ic_{h}d": v for h, v in stats.decay.items()},
            })

            details[factor] = {
                "stats": stats,
                "daily_ic": self.daily_ic(series, fwd[self.primary_horizon],
                                          method="pearson"),
                "daily_rank_ic": self.daily_ic(series, fwd[self.primary_horizon],
                                               method="spearman"),
                "quantile_returns": self.quantile_returns(
                    series, fwd[self.primary_horizon], self.n_quantiles
                ),
            }

        details["_correlation"] = corr_matrix
        summary = pd.DataFrame(summary_rows)
        if not summary.empty:
            summary = summary.sort_values("score", ascending=False)
        return summary, details

    def evaluate_factor(
        self, factor: pd.Series, fwd: pd.DataFrame
    ) -> FactorStats:
        """Evaluate a single factor series against precomputed forward returns."""
        stats = FactorStats(factor=factor.name or "factor")

        ic_p = self.daily_ic(factor, fwd[self.primary_horizon], "pearson")
        ic_s = self.daily_ic(factor, fwd[self.primary_horizon], "spearman")
        stats.n_days = int(ic_s.notna().sum())
        stats.ic_mean, stats.ic_std = self._series_moments(ic_p)
        stats.icir = stats.ic_mean / stats.ic_std if stats.ic_std > 0 else np.nan
        stats.ic_tstat = (
            stats.ic_mean / stats.ic_std * np.sqrt(stats.n_days)
            if stats.ic_std > 0 and stats.n_days > 0 else np.nan
        )
        stats.ic_positive_ratio = float((ic_p > 0).mean()) if len(ic_p) else np.nan
        stats.rank_ic_mean, stats.rank_ic_std = self._series_moments(ic_s)
        stats.rank_icir = (
            stats.rank_ic_mean / stats.rank_ic_std
            if stats.rank_ic_std > 0 else np.nan
        )
        stats.rank_ic_positive_ratio = (
            float((ic_s > 0).mean()) if len(ic_s) else np.nan
        )

        # IC decay across horizons
        for h in self.horizons:
            if h == self.primary_horizon:
                stats.decay[h] = stats.rank_ic_mean
            else:
                ic_h = self.daily_ic(factor, fwd[h], "spearman")
                stats.decay[h] = float(ic_h.mean()) if len(ic_h) else np.nan

        # Quantile analysis at primary horizon
        q_ret = self.quantile_returns(
            factor, fwd[self.primary_horizon], self.n_quantiles
        )
        if not q_ret.empty:
            daily_ls = q_ret.iloc[:, -1] - q_ret.iloc[:, 0]
            stats.long_short_ann = float(daily_ls.mean() * self.ppy)
            stats.monotonicity = self._monotonicity(q_ret.mean(axis=0).values)
            stats.turnover = self.factor_turnover(factor)

        return stats

    # ------------------------------------------------------------------
    # Core computations
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_close(close: pd.Series | pd.DataFrame) -> pd.Series:
        if isinstance(close, pd.DataFrame):
            if "close" not in close.columns:
                raise ValueError("close DataFrame must contain a 'close' column")
            close = close["close"]
        if not isinstance(close.index, pd.MultiIndex):
            raise ValueError("close must have MultiIndex (date, symbol)")
        return close.sort_index()

    def forward_returns(
        self, close: pd.Series, horizons: tuple[int, ...] | None = None
    ) -> pd.DataFrame:
        """Forward returns at multiple horizons.

        fwd_ret_h(t, s) = close(t+h, s) / close(t, s) - 1
        Computed per symbol with shift(-h), so each date's value uses
        only strictly future prices (no look-ahead at the observation point).
        """
        horizons = horizons or self.horizons
        close = self._extract_close(close)
        out = {}
        by_symbol = close.groupby(level="symbol")
        for h in horizons:
            out[h] = by_symbol.shift(-h) / close - 1.0
        df = pd.DataFrame(out)
        df.columns.name = "horizon"
        return df

    def daily_ic(
        self,
        factor: pd.Series,
        fwd_ret: pd.Series,
        method: str = "spearman",
    ) -> pd.Series:
        """Daily cross-sectional IC between factor and a forward-return horizon.

        Args:
            factor: Series with MultiIndex (date, symbol).
            fwd_ret: Series with matching index (one horizon).
            method: 'spearman' (RankIC) or 'pearson' (IC).

        Returns:
            Series of daily IC values indexed by date.
        """
        df = pd.concat(
            [factor.rename("factor"), fwd_ret.rename("fwd")], axis=1
        ).dropna()
        if df.empty:
            return pd.Series(dtype=float)

        def _ic(g: pd.DataFrame) -> float:
            if len(g) < self.min_cross_section:
                return np.nan
            if g["factor"].nunique() < 2 or g["fwd"].nunique() < 2:
                return np.nan
            if method == "spearman":
                return float(g["factor"].corr(g["fwd"], method="spearman"))
            return float(g["factor"].corr(g["fwd"], method="pearson"))

        return df.groupby(level="date").apply(_ic, include_groups=False)

    def quantile_returns(
        self,
        factor: pd.Series,
        fwd_ret: pd.Series,
        n_quantiles: int | None = None,
    ) -> pd.DataFrame:
        """Decile (quantile) mean forward returns per date.

        Returns:
            DataFrame indexed by date, columns Q1 (lowest factor) .. Qn
            (highest factor), values are mean forward return of each bucket.
        """
        n = n_quantiles or self.n_quantiles
        df = pd.concat(
            [factor.rename("factor"), fwd_ret.rename("fwd")], axis=1
        ).dropna()
        if df.empty:
            return pd.DataFrame()

        def _bucket(g: pd.DataFrame) -> pd.Series:
            if len(g) < self.min_cross_section or g["factor"].nunique() < n:
                return pd.Series(dtype=float)
            try:
                buckets = pd.qcut(
                    g["factor"].rank(method="first"), n,
                    labels=False, duplicates="drop",
                )
            except ValueError:
                return pd.Series(dtype=float)
            return g.groupby(buckets)["fwd"].mean()

        out = df.groupby(level="date").apply(_bucket, include_groups=False)
        if out.empty:
            return pd.DataFrame()
        out = pd.DataFrame(out)
        out.columns = [f"Q{i + 1}" for i in range(len(out.columns))]
        return out

    def factor_turnover(self, factor: pd.Series, top_frac: float = 0.1) -> float:
        """Top-quantile membership churn between consecutive dates.

        turnover_t = |Top_t \\ Top_{t-1}| / |Top_t|

        Low turnover (<0.2) = stable ranking = cheap to trade;
        high turnover (>0.5) = the factor rebalances aggressively.
        """
        df = factor.dropna()
        if df.empty:
            return np.nan

        top_sets: list[set] = []
        for _, cross in df.groupby(level="date"):
            if len(cross) < self.min_cross_section:
                continue
            k = max(int(len(cross) * top_frac), 1)
            top_sets.append(set(cross.nlargest(k).index.get_level_values("symbol")))

        if len(top_sets) < 2:
            return np.nan

        churn = [
            len(top_sets[i] - top_sets[i - 1]) / max(len(top_sets[i]), 1)
            for i in range(1, len(top_sets))
        ]
        return float(np.mean(churn))

    def correlation_matrix(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        """Mean daily cross-sectional Spearman correlation between factors.

        Values near |1| flag redundant factors that double-count the same
        exposure when combined with equal weights.
        """
        if factor_df.shape[1] < 2:
            return pd.DataFrame()
        valid = factor_df.dropna(how="all")
        if valid.empty:
            return pd.DataFrame()

        corr_frames = []
        for _, cross in valid.groupby(level="date"):
            cross = cross.droplevel("date")
            if len(cross) < self.min_cross_section:
                continue
            corr = cross.corr(method="spearman")
            if corr.notna().any().any():
                corr_frames.append(corr)

        if not corr_frames:
            return pd.DataFrame()
        return pd.concat(corr_frames).groupby(level=0).mean()

    # ------------------------------------------------------------------
    # Grading & reporting
    # ------------------------------------------------------------------

    @staticmethod
    def _series_moments(s: pd.Series) -> tuple[float, float]:
        s = s.dropna()
        if s.empty:
            return np.nan, np.nan
        return float(s.mean()), float(s.std())

    @staticmethod
    def _monotonicity(quantile_means: np.ndarray) -> float:
        if len(quantile_means) < 3 or np.isnan(quantile_means).any():
            return np.nan
        rho, _ = sps.spearmanr(np.arange(len(quantile_means)), quantile_means)
        return float(rho)

    def _grade(self, st: FactorStats) -> None:
        """Composite acceptance score and letter grade.

        Score blends the four mainstream acceptance criteria:
        RankIC magnitude, RankICIR stability, IC>0 consistency, and
        layered-return monotonicity. Thresholds follow broker research
        conventions: |RankIC| > 0.02, |ICIR| > 0.3, positive ratio > 0.55.
        """
        def _scaled(x: float, lo: float, hi: float) -> float:
            if np.isnan(x):
                return 0.0
            return float(np.clip((abs(x) - lo) / (hi - lo), 0.0, 1.0))

        score = (
            35.0 * _scaled(st.rank_ic_mean, 0.005, 0.06)          # alpha strength
            + 30.0 * _scaled(st.rank_icir, 0.05, 0.60)            # stability
            + 15.0 * _scaled(st.rank_ic_positive_ratio - 0.5, 0.0, 0.20)  # consistency
            + 20.0 * _scaled(st.monotonicity, 0.2, 0.9)           # monotonicity
        )
        st.score = round(score, 1)
        if score >= 70:
            st.grade = "A"
        elif score >= 50:
            st.grade = "B"
        elif score >= 30:
            st.grade = "C"
        else:
            st.grade = "D"

    def ic_ir_weights(self, summary: pd.DataFrame) -> pd.Series:
        """Compute IC-IR composite weights from an evaluation summary.

        w_i = rank_icir_i / Σ|rank_icir_j|

        Factors with near-zero IR get near-zero weight; negative-IR factors
        are excluded by default in the calling script (they should be
        reversed or dropped, not negatively weighted in a long-only book).
        """
        if summary.empty or "rank_icir" not in summary.columns:
            return pd.Series(dtype=float)
        ir = summary.set_index("factor")["rank_icir"].dropna()
        denom = ir.abs().sum()
        if denom <= 0:
            return pd.Series(dtype=float)
        return ir / denom

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def to_markdown(summary: pd.DataFrame, details: dict) -> str:
        """Render evaluation summary as a Markdown report."""
        lines = [
            "# 因子有效性评估报告",
            "",
            f"生成时间: {pd.Timestamp.now():%Y-%m-%d %H:%M}",
            f"评估因子数: {len(summary)}",
            "",
            "## 综合评分总表",
            "",
            summary.to_markdown(index=False, floatfmt=".4f"),
            "",
            "## 评级标准",
            "",
            "| 等级 | 分数 | 含义 |",
            "|------|------|------|",
            "| A | ≥70 | 强 alpha：可进组合并加大权重 |",
            "| B | 50-70 | 有效因子：标准权重 |",
            "| C | 30-50 | 弱因子：观察或与其他因子合成 |",
            "| D | <30 | 无效/反向：剔除或反向使用 |",
            "",
            "单项主流门槛：|RankIC| > 0.02，|RankICIR| > 0.3，IC>0 占比 > 0.55，分层单调性 > 0.5。",
            "",
        ]

        corr = details.get("_correlation")
        if corr is not None and not corr.empty:
            lines += [
                "## 因子相关性矩阵（日均横截面 Spearman）",
                "",
                "> |ρ| > 0.7 的因子对存在冗余，等权组合会重复暴露，建议保留 ICIR 更高的一只或做正交化。",
                "",
                corr.to_markdown(floatfmt=".2f"),
                "",
            ]

        for factor, det in details.items():
            if factor.startswith("_"):
                continue
            st: FactorStats = det["stats"]
            lines += [
                f"## {factor} — {st.grade} 级（{st.score} 分）",
                "",
                f"- RankIC 均值 {st.rank_ic_mean:.4f}，ICIR {st.rank_icir:.3f}，"
                f"IC>0 占比 {st.rank_ic_positive_ratio:.1%}",
                f"- 十分位多空年化价差 {st.long_short_ann:.2%}，"
                f"单调性 {st.monotonicity:.2f}，顶部分组换手率 {st.turnover:.1%}",
                f"- IC 衰减（RankIC）: "
                + ", ".join(f"{h}日 {v:.4f}" for h, v in st.decay.items()),
                "",
            ]
            q_ret = det.get("quantile_returns")
            if q_ret is not None and not q_ret.empty:
                means = q_ret.mean(axis=0)
                lines += [
                    "十分位分层平均前瞻收益（Q1=因子最低组，Qn=因子最高组）:",
                    "",
                    means.to_frame("mean_fwd_ret").to_markdown(floatfmt=".4f"),
                    "",
                ]

        return "\n".join(lines)
