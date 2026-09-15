"""Abstract broker interface for automated trading."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    LIMIT = "limit"      # 限价单
    MARKET = "market"    # 市价单


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class OrderResult:
    """Result of placing an order."""
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    status: OrderStatus = OrderStatus.PENDING
    message: str = ""
    filled_quantity: int = 0
    filled_price: float = 0.0


@dataclass
class AccountInfo:
    """Account balance and asset summary."""
    account_id: str
    total_asset: float = 0.0       # 总资产
    available_cash: float = 0.0    # 可用资金
    frozen_cash: float = 0.0       # 冻结资金
    market_value: float = 0.0      # 持仓市值
    total_return: float = 0.0      # 累计收益率


@dataclass
class Position:
    """Holding position."""
    symbol: str
    name: str = ""
    quantity: int = 0              # 持仓数量
    available: int = 0             # 可用数量
    avg_cost: float = 0.0          # 成本价
    current_price: float = 0.0     # 现价
    market_value: float = 0.0      # 市值
    profit_loss: float = 0.0       # 浮动盈亏
    profit_loss_pct: float = 0.0   # 盈亏比例


class BrokerInterface(ABC):
    """Abstract interface for broker trading operations."""

    name: str = "base"

    @abstractmethod
    def connect(self, **credentials) -> bool:
        """Connect to broker trading system.

        Returns:
            True if connection successful.
        """
        ...

    @abstractmethod
    def disconnect(self):
        """Disconnect from broker."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to broker."""
        ...

    @abstractmethod
    def get_account(self) -> Optional[AccountInfo]:
        """Query account asset and balance info."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Query current positions."""
        ...

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT,
        price: float = 0.0,
    ) -> OrderResult:
        """Submit a new order.

        Args:
            symbol: Stock code, e.g. '600519'.
            side: Buy or sell.
            quantity: Number of shares (must be multiple of 100 for A-shares).
            order_type: Limit or market order.
            price: Limit price (ignored for market orders).
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        ...

    @abstractmethod
    def get_orders(self, status: OrderStatus = None) -> list[OrderResult]:
        """Query today's orders, optionally filtered by status."""
        ...
