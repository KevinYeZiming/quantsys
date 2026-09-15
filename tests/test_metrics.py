"""Tests for performance metrics."""

import numpy as np
import pandas as pd
import pytest

from quantsys.utils.metrics import (
    compute_sharpe_ratio,
    compute_max_drawdown,
    compute_calmar_ratio,
    compute_annual_return,
    compute_win_rate,
    compute_turnover,
)


class TestMetrics:
    def test_sharpe_ratio_positive(self, sample_returns):
        """Test Sharpe ratio with positive mean returns."""
        # Create returns with positive drift
        positive = sample_returns + 0.001  # Add small positive drift
        sharpe = compute_sharpe_ratio(positive)
        assert sharpe > 0

    def test_sharpe_ratio_zero_vol(self):
        """Test Sharpe ratio with zero volatility."""
        zero_vol = pd.Series([0.001] * 252)
        sharpe = compute_sharpe_ratio(zero_vol)
        assert sharpe == 0.0

    def test_max_drawdown(self, sample_returns):
        """Test max drawdown calculation."""
        max_dd, peak, trough = compute_max_drawdown(sample_returns)
        assert max_dd <= 0  # Drawdown is negative
        assert isinstance(max_dd, float)

    def test_calmar_ratio(self, sample_returns):
        """Test Calmar ratio."""
        calmar = compute_calmar_ratio(sample_returns)
        assert isinstance(calmar, float)

    def test_annual_return(self, sample_returns):
        """Test annualized return."""
        ann_ret = compute_annual_return(sample_returns)
        assert isinstance(ann_ret, float)

    def test_win_rate_range(self, sample_returns):
        """Test win rate is between 0 and 1."""
        win_rate = compute_win_rate(sample_returns)
        assert 0 <= win_rate <= 1

    def test_turnover_equal_weights(self):
        """Test turnover with identical weights."""
        weights = pd.Series([0.1] * 10, index=[f"s{i}" for i in range(10)])
        turnover = compute_turnover(weights, weights)
        assert turnover == 0.0

    def test_turnover_full_rotation(self):
        """Test turnover with complete portfolio rotation."""
        before = pd.Series({"A": 1.0, "B": 0.0})
        after = pd.Series({"A": 0.0, "B": 1.0})
        turnover = compute_turnover(before, after)
        assert turnover == 1.0
