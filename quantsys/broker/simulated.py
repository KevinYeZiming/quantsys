"""Simulated broker for strategy testing without a live account.

Mimics a real broker API with virtual cash, positions, and
order execution. Used as fallback when QMT is not installed.
"""

import logging
import uuid
from datetime import datetime

import pandas as pd

from quantsys.broker.base import (
    AccountInfo,
    BrokerInterface,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

logger = logging.getLogger(__name__)


class SimulatedBroker(BrokerInterface):
    """In-memory simulated broker for local testing.

    Useful for:
    - Testing strategy logic end-to-end before live deployment
    - Paper trading with real market data
    - CI/CD pipeline testing
    """

    name = "simulated"

    def __init__(self, initial_capital: float = 1_000_000.0):
        self._initial_capital = initial_capital
        self._connected = False
        self._account = AccountInfo(
            account_id="sim_001",
            total_asset=initial_capital,
            available_cash=initial_capital,
        )
        self._positions: dict[str, Position] = {}
        self._orders: list[OrderResult] = []
        self._order_history: list[OrderResult] = []

    # -- Connection ---------------------------------------------------------

    def connect(self, **credentials) -> bool:
        logger.info(f"Simulated broker connected (capital: ¥{self._initial_capital:,.0f})")
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False
        logger.info("Simulated broker disconnected")

    def is_connected(self) -> bool:
        return self._connected

    # -- Account ------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        self._recalculate_account()
        return self._account

    def _recalculate_account(self):
        """Update account with current position values."""
        mv = sum(p.market_value for p in self._positions.values())
        self._account.market_value = mv
        self._account.total_asset = self._account.available_cash + mv
        if self._initial_capital > 0:
            self._account.total_return = (
                self._account.total_asset / self._initial_capital - 1.0
            )

    # -- Positions ----------------------------------------------------------

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def update_price(self, symbol: str, price: float):
        """Update the current market price for a position (for paper trading)."""
        if symbol in self._positions:
            pos = self._positions[symbol]
            pos.current_price = price
            pos.market_value = pos.quantity * price
            pos.profit_loss = (price - pos.avg_cost) * pos.quantity
            if pos.avg_cost > 0:
                pos.profit_loss_pct = (price / pos.avg_cost - 1.0) * 100
        self._recalculate_account()

    def update_prices(self, prices: dict[str, float]):
        """Batch update prices from market data."""
        for symbol, price in prices.items():
            self.update_price(symbol, price)

    # -- Orders -------------------------------------------------------------

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT,
        price: float = 0.0,
    ) -> OrderResult:
        if not self._connected:
            return OrderResult(
                order_id="", symbol=symbol, side=side, quantity=quantity,
                price=price, status=OrderStatus.REJECTED,
                message="Not connected",
            )

        if quantity % 100 != 0:
            return OrderResult(
                order_id="", symbol=symbol, side=side, quantity=quantity,
                price=price, status=OrderStatus.REJECTED,
                message="A-share order quantity must be multiple of 100",
            )

        order_id = str(uuid.uuid4())[:8]
        exec_price = price if price > 0 else self._get_market_price(symbol)

        # Check cash for buys
        if side == OrderSide.BUY:
            cost = exec_price * quantity
            commission = max(5.0, cost * 0.00025)
            total_cost = cost + commission
            if total_cost > self._account.available_cash:
                return OrderResult(
                    order_id=order_id, symbol=symbol, side=side,
                    quantity=quantity, price=price,
                    status=OrderStatus.REJECTED,
                    message=f"Insufficient cash: need ¥{total_cost:,.0f}, have ¥{self._account.available_cash:,.0f}",
                )

            self._account.available_cash -= total_cost
            self._account.frozen_cash += total_cost

        # Check holdings for sells
        if side == OrderSide.SELL:
            pos = self._positions.get(symbol)
            if not pos or pos.available < quantity:
                return OrderResult(
                    order_id=order_id, symbol=symbol, side=side,
                    quantity=quantity, price=price,
                    status=OrderStatus.REJECTED,
                    message=f"Insufficient position: have {pos.available if pos else 0}, need {quantity}",
                )

        # Execute
        result = OrderResult(
            order_id=order_id, symbol=symbol, side=side,
            quantity=quantity, price=exec_price,
            status=OrderStatus.FILLED,
            message="Filled (simulated)",
            filled_quantity=quantity,
            filled_price=exec_price,
        )
        self._orders.append(result)
        self._order_history.append(result)

        # Update position
        if side == OrderSide.BUY:
            if symbol in self._positions:
                pos = self._positions[symbol]
                total_cost = pos.avg_cost * pos.quantity + exec_price * quantity
                pos.quantity += quantity
                pos.available += quantity
                pos.avg_cost = total_cost / pos.quantity if pos.quantity else 0
            else:
                self._positions[symbol] = Position(
                    symbol=symbol, quantity=quantity, available=quantity,
                    avg_cost=exec_price, current_price=exec_price,
                    market_value=exec_price * quantity,
                )
            self._account.frozen_cash -= exec_price * quantity
        else:
            pos = self._positions[symbol]
            pos.quantity -= quantity
            pos.available -= quantity
            if pos.quantity <= 0:
                del self._positions[symbol]
            sale_proceeds = exec_price * quantity * (1 - 0.00025 - 0.0005)
            self._account.available_cash += sale_proceeds

        self._recalculate_account()
        logger.info(f"[SIM] {side.value.upper()} {quantity} {symbol} @ {exec_price:.2f}")
        return result

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id:
                o.status = OrderStatus.CANCELLED
                o.message = "Cancelled"
                self._orders.remove(o)
                return True
        return False

    def get_orders(self, status: OrderStatus = None) -> list[OrderResult]:
        if status:
            return [o for o in self._orders if o.status == status]
        return list(self._orders)

    def _get_market_price(self, symbol: str) -> float:
        """Get last known price for a symbol (for market orders)."""
        pos = self._positions.get(symbol)
        if pos and pos.current_price > 0:
            return pos.current_price
        return 10.0  # Default fallback
