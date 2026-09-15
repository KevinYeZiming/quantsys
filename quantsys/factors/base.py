"""Abstract base class for all factors."""

from abc import ABC, abstractmethod

import pandas as pd


class BaseFactor(ABC):
    """Abstract factor definition.

    Each factor is a class with:
    - name: unique factor identifier
    - category: one of 'value', 'momentum', 'volatility', 'liquidity', 'technical', 'alternative'
    - frequency: 'daily' or 'monthly'
    - requires: list of required data fields

    Subclasses must implement compute() which takes a panel DataFrame
    and returns a Series of factor values.
    """

    name: str = "base"
    category: str = "value"
    frequency: str = "monthly"
    requires: list[str] = []

    @abstractmethod
    def compute(self, panel: pd.DataFrame) -> pd.Series:
        """Compute factor values for a cross-section of stocks.

        Args:
            panel: DataFrame with MultiIndex (date, symbol) containing
                   required columns for factor computation.

        Returns:
            Series with same index as panel, containing factor values.
            Higher values should correspond to higher expected returns
            (positive alpha direction), following convention from
            the Chinese academic literature (Zhu Yifeng, 2025).
        """
        ...

    def is_valid(self, result: pd.Series) -> bool:
        """Check if factor computation produced valid results.

        Returns True if >= 30% of values are non-NaN.
        """
        if result is None or len(result) == 0:
            return False
        coverage = result.notna().mean()
        return coverage >= 0.30

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', category='{self.category}')"
