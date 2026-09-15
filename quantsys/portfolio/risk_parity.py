"""Risk parity portfolio optimization.

Implements standard risk parity and Hierarchical Risk Parity (HRP)
for Chinese A-share and ETF portfolios.
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


class RiskParityOptimizer:
    """Risk parity portfolio construction.

    Provides naive (equal risk contribution) and HRP (Hierarchical Risk Parity)
    for A-share/ETF portfolios where expected returns are noisy.

    Usage::

        rp = RiskParityOptimizer()
        weights = rp.naive_rp(returns.cov())
        weights_hrp = rp.hrp(returns)
    """

    def naive_rp(self, cov_matrix: pd.DataFrame, max_iter: int = 100) -> np.ndarray:
        """Compute naive risk parity weights.

        Each asset contributes equal risk:
            w_i * (Cov * w)_i = constant for all i

        Args:
            cov_matrix: Covariance matrix.
            max_iter: Maximum iterations for convergence.

        Returns:
            Array of weights summing to 1.0.
        """
        n = len(cov_matrix)
        if n == 0:
            return np.array([])
        if n == 1:
            return np.array([1.0])

        cov = cov_matrix.values
        vols = np.sqrt(np.diag(cov))

        # Initial weights: inverse volatility
        w = (1.0 / np.where(vols > 0, vols, 1.0))
        w = w / w.sum()

        # Iterate to equalize risk contributions
        for _ in range(max_iter):
            sigma_w = cov @ w
            risk_contrib = w * sigma_w
            target_risk = risk_contrib.mean()

            if np.allclose(risk_contrib, target_risk, rtol=1e-4):
                break

            # Adjust weights toward equal risk contribution
            adj = target_risk / np.where(risk_contrib > 0, risk_contrib, 1.0)
            w = w * adj
            w = w / w.sum()

        return w

    def hrp(self, returns: pd.DataFrame) -> list[int]:
        """Hierarchical Risk Parity (HRP).

        De Prado's HRP algorithm:
        1. Compute correlation-based distance matrix
        2. Hierarchical clustering
        3. Quasi-diagonalization
        4. Recursive bisection risk allocation

        Args:
            returns: DataFrame of asset returns (columns = assets).

        Returns:
            List of asset indices in quasi-diagonal order (for recursive bisection).
        """
        corr = returns.corr().values
        dist = np.sqrt(0.5 * (1 - corr))
        distance_vector = squareform(dist, checks=False)
        linkage_matrix = linkage(distance_vector, method="ward")
        return linkage_matrix

    def get_clusters(
        self, returns: pd.DataFrame, n_clusters: int = 5
    ) -> pd.Series:
        """Cluster assets for hierarchical allocation.

        Args:
            returns: DataFrame of asset returns.
            n_clusters: Number of clusters.

        Returns:
            Series mapping asset name to cluster label.
        """
        linkage_matrix = self.hrp(returns)
        labels = fcluster(linkage_matrix, n_clusters, criterion="maxclust")
        return pd.Series(labels, index=returns.columns)

    def equal_risk_contribution(
        self, returns: pd.DataFrame, lookback: int = 60
    ) -> pd.Series:
        """Compute equal risk contribution weights.

        Quick approximation: w_i = 1/vol_i / sum(1/vol_j).

        Args:
            returns: DataFrame of asset returns.
            lookback: Lookback window for volatility estimation.

        Returns:
            Series of weights.
        """
        vols = returns.tail(lookback).std() * np.sqrt(252)
        vols = vols.replace(0, pd.NA)

        inv_vols = 1.0 / vols
        weights = inv_vols / inv_vols.sum()
        return weights.fillna(0)
