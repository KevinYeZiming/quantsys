"""Tests for the factor evaluation framework (synthetic data, no network)."""

import numpy as np
import pandas as pd
import pytest

from quantsys.factors.evaluation import FactorEvaluator


@pytest.fixture
def synthetic_panel():
    """Build a synthetic (date, symbol) panel where a known signal exists.

    - 40 symbols x 300 trading days
    - 'alpha_signal' genuinely predicts next-5d returns (RankIC > 0)
    - 'noise_signal' is pure noise (RankIC ~ 0)
    """
    rng = np.random.default_rng(42)
    n_days, n_symbols = 300, 40
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    symbols = [f"{600000 + i}" for i in range(n_symbols)]

    # Per-symbol random walk prices
    rets = rng.normal(0.0003, 0.02, size=(n_days, n_symbols))
    close = 20 * np.exp(np.cumsum(rets, axis=0))
    close_df = pd.DataFrame(close, index=dates, columns=symbols)

    # True signal: slow-moving latent strength per symbol
    latent = rng.normal(0, 1, size=n_symbols)
    signal = np.tile(latent, (n_days, 1)) + rng.normal(0, 0.3, size=(n_days, n_symbols))
    noise = rng.normal(0, 1, size=(n_days, n_symbols))

    # Inject predictive power: next-5d return co-moves with signal
    for t in range(n_days - 5):
        k = 0.003
        rets[t + 5] += k * signal[t]

    close_df = pd.DataFrame(20 * np.exp(np.cumsum(rets, axis=0)))
    index = pd.MultiIndex.from_product(
        [dates, symbols], names=["date", "symbol"]
    )
    close = pd.Series(close_df.values.ravel(), index=index, name="close")

    factor_df = pd.DataFrame({
        "alpha_signal": signal.ravel(),
        "noise_signal": noise.ravel(),
    }, index=index)

    return factor_df, close


def test_forward_returns_no_lookback(synthetic_panel):
    _, close = synthetic_panel
    ev = FactorEvaluator()
    fwd = ev.forward_returns(close, (5,))
    h5 = fwd[5]
    # Recompute manually for one point
    df = close.unstack("symbol").sort_index()
    manual = df.shift(-5) / df - 1.0
    sample = h5.unstack("symbol")
    pd.testing.assert_frame_equal(
        sample.sort_index(axis=1), manual.sort_index(axis=1), check_dtype=False
    )


def test_daily_rank_ic_detects_signal(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    fwd = ev.forward_returns(close, (5,))
    ic = ev.daily_ic(factor_df["alpha_signal"], fwd[5], method="spearman")
    assert ic.notna().sum() > 100
    assert ic.mean() > 0.03, f"signal RankIC should be positive, got {ic.mean()}"


def test_noise_factor_has_low_ic(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    fwd = ev.forward_returns(close, (5,))
    ic = ev.daily_ic(factor_df["noise_signal"], fwd[5], method="spearman")
    assert abs(ic.mean()) < 0.03


def test_evaluate_all_summary(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    summary, details = ev.evaluate_all(factor_df, close)

    assert len(summary) == 2
    assert set(summary["factor"]) == {"alpha_signal", "noise_signal"}
    # alpha factor must outscore noise factor
    row = summary.set_index("factor")
    assert row.loc["alpha_signal", "score"] > row.loc["noise_signal", "score"]
    # decay dict present for all horizons
    for h in (1, 3, 5, 10, 20):
        assert f"rank_ic_{h}d" in summary.columns
    # correlation matrix present
    corr = details["_correlation"]
    assert corr.shape == (2, 2)


def test_quantile_monotonicity(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    fwd = ev.forward_returns(close, (5,))
    q_ret = ev.quantile_returns(factor_df["alpha_signal"], fwd[5], 5)
    assert not q_ret.empty
    means = q_ret.mean(axis=0).values
    rho = ev._monotonicity(means)
    assert rho > 0.5, f"quantile means should rise with signal, rho={rho}"


def test_turnover_bounds(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    to = ev.factor_turnover(factor_df["noise_signal"], top_frac=0.1)
    assert 0.0 <= to <= 1.0


def test_ic_ir_weights(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    summary, _ = ev.evaluate_all(factor_df, close)
    w = ev.ic_ir_weights(summary)
    assert abs(w.sum()) > 0.99
    # alpha signal should carry most weight
    assert w["alpha_signal"] > 0.5


def test_markdown_report(synthetic_panel):
    factor_df, close = synthetic_panel
    ev = FactorEvaluator(min_cross_section=20)
    summary, details = ev.evaluate_all(factor_df, close)
    md = ev.to_markdown(summary, details)
    assert "因子有效性评估报告" in md
    assert "alpha_signal" in md
    assert "因子相关性矩阵" in md
