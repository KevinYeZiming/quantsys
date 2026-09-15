"""Performance and risk metrics for quantitative strategies."""

import numpy as np
import pandas as pd


def compute_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.015,
    annualize: bool = True,
    trading_days: int = 252,
) -> float:
    """Compute annualized Sharpe ratio.

    Args:
        returns: Daily return series.
        risk_free_rate: Annual risk-free rate.
        annualize: Whether to annualize.
        trading_days: Number of trading days per year.

    Returns:
        Sharpe ratio.
    """
    excess = returns - risk_free_rate / trading_days
    if excess.std() < 1e-12:
        return 0.0
    ratio = excess.mean() / excess.std()
    if annualize:
        ratio *= np.sqrt(trading_days)
    return float(ratio)


def compute_max_drawdown(returns: pd.Series) -> tuple[float, pd.Timestamp | None, pd.Timestamp | None]:
    """Compute maximum drawdown from daily returns.

    Returns:
        Tuple of (max_drawdown, peak_date, trough_date).
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_dd = drawdown.min()
    trough_date = drawdown.idxmin() if isinstance(returns.index, pd.DatetimeIndex) else None
    peak_date = running_max.loc[:trough_date].idxmax() if trough_date else None
    return float(max_dd), peak_date, trough_date


def compute_calmar_ratio(returns: pd.Series, trading_days: int = 252) -> float:
    """Compute Calmar ratio (annual return / max drawdown)."""
    ann_ret = compute_annual_return(returns, trading_days)
    max_dd, _, _ = compute_max_drawdown(returns)
    if max_dd == 0:
        return 0.0
    return ann_ret / abs(max_dd)


def compute_information_coefficient(
    factor_values: pd.Series,
    forward_returns: pd.Series,
    method: str = "spearman",
) -> float:
    """Compute Information Coefficient (IC) between factor and forward returns.

    Args:
        factor_values: Factor values cross-sectionally.
        forward_returns: Forward period returns.
        method: 'spearman' for RankIC or 'pearson' for Pearson IC.

    Returns:
        IC value.
    """
    mask = factor_values.notna() & forward_returns.notna()
    if mask.sum() < 10:
        return np.nan
    if method == "spearman":
        return float(factor_values[mask].corr(forward_returns[mask], method="spearman"))
    else:
        return float(factor_values[mask].corr(forward_returns[mask], method="pearson"))


def compute_information_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Compute Information Ratio (tracking error adjusted excess return)."""
    excess = returns - benchmark_returns
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(252))


def compute_annual_return(returns: pd.Series, trading_days: int = 252) -> float:
    """Compute annualized return from daily returns."""
    cumulative = (1 + returns).prod()
    n_years = len(returns) / trading_days
    if n_years == 0:
        return 0.0
    return float(cumulative ** (1 / n_years) - 1)


def compute_win_rate(returns: pd.Series) -> float:
    """Compute win rate (proportion of positive return days)."""
    return float((returns > 0).mean())


def compute_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.015,
    trading_days: int = 252,
) -> float:
    """Compute Sortino ratio using downside deviation."""
    excess = returns - risk_free_rate / trading_days
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    ratio = excess.mean() / downside.std()
    return float(ratio * np.sqrt(trading_days))


def compute_turnover(weights_before: pd.Series, weights_after: pd.Series) -> float:
    """Compute one-way turnover between two weight vectors."""
    aligned = pd.concat([weights_before, weights_after], axis=1, keys=["before", "after"]).fillna(0)
    return float((aligned["after"] - aligned["before"]).abs().sum() / 2)
