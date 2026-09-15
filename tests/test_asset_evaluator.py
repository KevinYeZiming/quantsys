"""Tests for the unified asset evaluator (synthetic data, no network)."""

import json
import numpy as np
import pandas as pd
import pytest

from quantsys.advisor.asset_evaluator import AssetAction, AssetEvaluator
from quantsys.data.sources.cache import CacheManager
from quantsys.data.sources.funds import FundSource
from quantsys.data.sources.gold import GoldSource


@pytest.fixture
def cache(tmp_path):
    return CacheManager(tmp_path / "raw")


@pytest.fixture
def evaluator(cache):
    return AssetEvaluator(cache_dir=cache.cache_dir)


def _write_stock(cache, symbol, trend="up", n=400, seed=1):
    rng = np.random.default_rng(seed)
    drift = {"up": 0.002, "down": -0.002, "flat": 0.0}[trend]
    # small noise (0.2%) so 60d drift (~±12%) is never overwhelmed —
    # keeps the trend label unambiguous for ranking assertions
    rets = rng.normal(drift, 0.002, n)
    close = pd.Series(20 * np.exp(np.cumsum(rets)),
                      index=pd.bdate_range("2025-01-02", periods=n),
                      name="close")
    df = pd.DataFrame({"close": close, "volume": 1e6, "amount": close * 1e6})
    cache.put(df, "stock_daily", symbol=symbol)
    return df


def _write_fund_nav(cache, symbol, n=400, seed=2):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0008, 0.008, n)
    nav = pd.Series(np.exp(np.cumsum(rets)),
                    index=pd.bdate_range("2025-01-02", periods=n), name="nav")
    cache.put(pd.DataFrame({"nav": nav}), "fund_nav", symbol=symbol)
    return nav


def _write_gold_etf(cache, symbol, n=400, seed=3):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.001, 0.012, n)
    close = pd.Series(5 * np.exp(np.cumsum(rets)),
                      index=pd.bdate_range("2025-01-02", periods=n), name="close")
    cache.put(pd.DataFrame({"close": close}), "gold_etf", symbol=symbol)
    return close


# ---------------------------------------------------------------------------
# AssetEvaluator
# ---------------------------------------------------------------------------

def test_evaluate_stock_up_trend(evaluator, cache):
    _write_stock(cache, "600001", trend="up")
    results = evaluator.evaluate([("600001", "stock")], "2026-09-01")
    assert len(results) == 1
    r = results[0]
    assert r.asset_type == "stock"
    assert r.price > 0
    # strong uptrend → trend/momentum scores high → overall bullish action
    assert r.action in (AssetAction.BUY, AssetAction.STRONG_BUY, AssetAction.HOLD)
    assert r.trend_score > 60
    assert r.stop_loss < r.price < r.take_profit
    assert r.reasons


def test_evaluate_stock_down_trend(evaluator, cache):
    _write_stock(cache, "600002", trend="down", seed=7)
    results = evaluator.evaluate([("600002", "stock")], "2026-09-01")
    r = results[0]
    assert r.total_score < 60
    assert r.action in (AssetAction.SELL, AssetAction.STRONG_SELL, AssetAction.HOLD)


def test_evaluate_fund_and_gold(evaluator, cache):
    _write_fund_nav(cache, "017103")
    _write_gold_etf(cache, "518880")
    results = evaluator.evaluate(
        [("017103", "fund"), ("518880", "gold")], "2026-09-01"
    )
    assert {r.asset_type for r in results} == {"fund", "gold"}
    for r in results:
        assert r.price > 0
        assert 0 <= r.total_score <= 100
        assert r.action in set(AssetAction)


def test_evaluate_missing_data(evaluator):
    results = evaluator.evaluate([("999999", "stock")], "2026-09-01")
    r = results[0]
    assert any("无本地数据" in f for f in r.risk_flags)


def test_evaluate_positions_with_cost(evaluator, cache):
    _write_stock(cache, "600003", trend="up", seed=11)
    positions = [{"symbol": "600003", "name": "测试股", "asset_type": "stock",
                  "quantity": 100, "avg_cost": 15.0, "added_date": "2026-01-01"}]
    results = evaluator.evaluate_positions(positions, "2026-09-01")
    assert len(results) == 1
    assert "pnl_pct" in results[0].metrics


def test_select_stocks_ranking(evaluator, cache):
    _write_stock(cache, "600010", trend="up", seed=21)
    _write_stock(cache, "600011", trend="down", seed=22)
    _write_stock(cache, "600012", trend="up", seed=23)
    ranked = evaluator.select_stocks(["600010", "600011", "600012"],
                                     "2026-09-01", top_n=3)
    assert len(ranked) == 3
    # up-trend stocks should outrank the down-trend one on average
    scores = {r.symbol: r.total_score for r in ranked}
    assert scores["600011"] < max(scores["600010"], scores["600012"])


def test_save_and_markdown(evaluator, cache, tmp_path):
    _write_stock(cache, "600020", trend="up", seed=31)
    results = evaluator.evaluate([("600020", "stock")], "2026-09-01")
    path = evaluator.save(results, out_dir=tmp_path / "evals")
    assert path.exists()
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "600020"
    md = evaluator.to_markdown(results)
    assert "买卖评估报告" in md and "600020" in md


def test_evaluate_etf_from_cache(evaluator, cache):
    """ETF holdings must load from the etf_daily cache."""
    n = 400
    rng = np.random.default_rng(41)
    rets = rng.normal(0.001, 0.008, n)
    close = pd.Series(2.0 * np.exp(np.cumsum(rets)),
                      index=pd.bdate_range("2025-01-02", periods=n), name="close")
    cache.put(pd.DataFrame({"close": close}), "etf_daily", symbol="515080")
    results = evaluator.evaluate([("515080", "etf")], "2026-09-01")
    r = results[0]
    assert r.asset_type == "etf"
    assert r.price > 0
    assert r.metrics["data_source"] == "etf_daily"
    assert r.action in set(AssetAction)


# ---------------------------------------------------------------------------
# FundSource / GoldSource (network-free via monkeypatched _call)
# ---------------------------------------------------------------------------

def test_fund_nav_normalization(cache, monkeypatch):
    raw = pd.DataFrame({
        "净值日期": ["2026-09-10", "2026-09-11", "2026-09-12"],
        "单位净值": ["1.2340", "1.2450", "1.2400"],
        "日增长率": ["0.50", "0.89", "-0.40"],
    })
    src = FundSource(cache)
    monkeypatch.setattr(src, "_call", lambda *a, **k: raw)
    nav = src.update_nav("017103")
    assert list(nav.columns) == ["nav", "daily_return_pct"]
    assert len(nav) == 3
    assert nav.index.name == "date"
    # second call hits cache → same result
    nav2 = src.update_nav("017103")
    assert len(nav2) == 3


def test_fund_info_transpose(monkeypatch):
    raw = pd.DataFrame({"item": ["基金类型", "成立日期", "资产规模"],
                        "value": ["混合型", "2021-06-01", "12.5亿元"]})
    src = FundSource(None)
    monkeypatch.setattr(src, "_call", lambda *a, **k: raw)
    info = src.get_info("017103")
    assert info.iloc[0]["基金类型"] == "混合型"
    assert info.iloc[0]["symbol"] == "017103"


def test_gold_spot_normalization(cache, monkeypatch):
    raw = pd.DataFrame({
        "日期": ["2026-09-10", "2026-09-11"],
        "开盘价": [550.0, 552.0], "最高价": [555.0, 556.0],
        "最低价": [548.0, 551.0], "收盘价": [553.5, 554.8],
    })
    src = GoldSource(cache)
    monkeypatch.setattr(src, "_call", lambda *a, **k: raw)
    spot = src.update_spot("Au99.99")
    assert spot.index.name == "date"
    assert "close" in spot.columns and len(spot) == 2
