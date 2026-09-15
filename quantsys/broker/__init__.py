"""Broker integration for automated trading.

Supports Galaxy Securities (银河证券) via QMT (量化交易终端) and
Easytrader GUI automation as fallback.
"""

from quantsys.broker.base import BrokerInterface, OrderResult
from quantsys.broker.galaxy_qmt import GalaxyQMTBroker
from quantsys.broker.simulated import SimulatedBroker

__all__ = ["BrokerInterface", "OrderResult", "GalaxyQMTBroker", "SimulatedBroker"]
