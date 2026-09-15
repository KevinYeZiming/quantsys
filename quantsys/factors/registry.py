"""Factor registry for automatic discovery and management.

Scans factor category modules and provides a unified interface for
loading, configuring, and computing all factors.
"""

import importlib
import logging
from typing import Type

import pandas as pd

from quantsys.factors.base import BaseFactor

logger = logging.getLogger(__name__)

# Maps factor class names to their module paths
_FACTOR_MODULES = {
    # Value
    "ROEFactor": "quantsys.factors.value",
    "ROAFactor": "quantsys.factors.value",
    "EPFactor": "quantsys.factors.value",
    "BPFactor": "quantsys.factors.value",
    "CFPFactor": "quantsys.factors.value",
    # Momentum
    "Momentum12M1M": "quantsys.factors.momentum",
    "Momentum60D": "quantsys.factors.momentum",
    "ShortTermReversal": "quantsys.factors.momentum",
    # Volatility
    "IdioVolatility": "quantsys.factors.volatility",
    "VolatilitySkew": "quantsys.factors.volatility",
    "Amplitude20D": "quantsys.factors.volatility",
    # Liquidity
    "Turnover20D": "quantsys.factors.liquidity",
    "VolumeCorrelation": "quantsys.factors.liquidity",
    "AmihudIlliq": "quantsys.factors.liquidity",
    # Technical
    "RSIFactor": "quantsys.factors.technical",
    "MACDDivergence": "quantsys.factors.technical",
    "MADeviation": "quantsys.factors.technical",
    # Alternative
    "SmartMoneyFlow": "quantsys.factors.alternative",
    "SalienceTheory": "quantsys.factors.alternative",
    "MaxEffect": "quantsys.factors.alternative",
}


class FactorRegistry:
    """Registry of all available factors, auto-discovered from factor modules.

    Usage::

        registry = FactorRegistry()
        registry.load_all()

        # Get a specific factor instance
        roe = registry.get("ROEFactor", periods=4)

        # Compute all enabled factors on a panel
        factor_df = registry.compute_all(panel, config=factors_config)
    """

    def __init__(self):
        self._classes: dict[str, Type[BaseFactor]] = {}
        self._instances: dict[str, BaseFactor] = {}

    def discover(self):
        """Auto-discover all factor classes from registered modules."""
        for class_name, module_path in _FACTOR_MODULES.items():
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name, None)
                if cls is not None and issubclass(cls, BaseFactor):
                    self._classes[class_name] = cls
                else:
                    logger.warning(f"Factor class {class_name} not found in {module_path}")
            except ImportError as e:
                logger.warning(f"Failed to import {module_path}: {e}")

        logger.info(f"Discovered {len(self._classes)} factor classes")

    def get(self, class_name: str, **kwargs) -> BaseFactor:
        """Get a factor instance by class name.

        Args:
            class_name: Factor class name, e.g. 'ROEFactor'.
            **kwargs: Constructor arguments for the factor.

        Returns:
            Factor instance.
        """
        if class_name not in self._classes:
            raise KeyError(f"Unknown factor class: {class_name}. Available: {list(self._classes)}")

        # Cache instances by class_name + kwargs
        cache_key = class_name + str(sorted(kwargs.items()))
        if cache_key not in self._instances:
            self._instances[cache_key] = self._classes[class_name](**kwargs)

        return self._instances[cache_key]

    def list_all(self) -> list[str]:
        """List all available factor class names."""
        return list(self._classes.keys())

    def list_by_category(self, category: str) -> list[str]:
        """List factor class names by category."""
        return [
            name for name, cls in self._classes.items()
            if cls().category == category
        ]

    def compute_all(
        self,
        panel: pd.DataFrame,
        config: dict = None,
    ) -> pd.DataFrame:
        """Compute all enabled factors on a data panel.

        Args:
            panel: DataFrame with MultiIndex (date, symbol) containing OHLCV
                   and financial data columns.
            config: Factor configuration dict (from factors.yaml). If None,
                    computes all discovered factors with defaults.

        Returns:
            DataFrame with same index as panel, one column per factor.
        """
        factor_dfs = []

        if config is None:
            # Compute all factors with defaults
            for class_name in self._classes:
                try:
                    factor = self._classes[class_name]()
                    values = factor.compute(panel)
                    values.name = factor.name
                    factor_dfs.append(values)
                    logger.debug(f"Computed factor: {factor.name}")
                except Exception as e:
                    logger.warning(f"Failed to compute {class_name}: {e}")

        else:
            factor_configs = config.get("factors", {})
            if not factor_configs:
                # Config provided but no "factors" key — compute all with defaults
                for class_name in self._classes:
                    try:
                        factor = self._classes[class_name]()
                        values = factor.compute(panel)
                        values.name = factor.name
                        factor_dfs.append(values)
                        logger.debug(f"Computed factor: {factor.name}")
                    except Exception as e:
                        logger.warning(f"Failed to compute {class_name}: {e}")
                if not factor_dfs:
                    return pd.DataFrame()
                return pd.concat(factor_dfs, axis=1)

            for factor_name, factor_cfg in factor_configs.items():
                if not factor_cfg.get("enabled", True):
                    continue

                class_name = factor_cfg.get("class")
                if class_name is None:
                    logger.warning(f"No class specified for factor '{factor_name}'")
                    continue

                try:
                    # Extract kwargs from config, excluding 'class' and 'enabled'
                    kwargs = {k: v for k, v in factor_cfg.items() if k not in ("class", "enabled", "category")}
                    factor = self.get(class_name, **kwargs)
                    values = factor.compute(panel)
                    values.name = factor.name
                    factor_dfs.append(values)
                    logger.debug(f"Computed factor: {factor.name}")
                except Exception as e:
                    logger.warning(f"Failed to compute factor {factor_name} ({class_name}): {e}")

        if not factor_dfs:
            return pd.DataFrame()

        return pd.concat(factor_dfs, axis=1)
