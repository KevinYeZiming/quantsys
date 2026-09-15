"""Galaxy Securities (银河证券) QMT automated trading adapter.

Galaxy Securities provides the QMT (量化交易终端) platform for
algorithmic trading. The Python API (`xtquant`) allows programmatic
order submission, position queries, and account management.

Prerequisites:
    1. Open a Galaxy Securities account and apply for QMT access
    2. Install the QMT terminal from https://www.glsc.com.cn/
    3. Install xtquant: pip install xtquant (provided by QMT)
    4. Log in to QMT terminal with your account credentials
    5. Enable API access in QMT settings

API Reference:
    Official doc: https://www.glsc.com.cn/qmt/doc/

Usage::

    from quantsys.broker import GalaxyQMTBroker
    from quantsys.security import CredentialManager

    cred = CredentialManager()
    broker = GalaxyQMTBroker(credential_manager=cred)
    broker.connect()

    # Get account info
    account = broker.get_account()

    # Submit buy order: 100 shares of Moutai at limit 1800
    result = broker.submit_order("600519", OrderSide.BUY, 100,
                                  OrderType.LIMIT, 1800.0)
"""

import logging
import os
from pathlib import Path
from typing import Optional

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

# xtquant is provided by the QMT installation, may not be importable
# in environments without QMT terminal installed.
_XTQUANT_AVAILABLE = False
try:
    from xtquant import xtdata, xttrader
    from xtquant.xttype import StockAccount
    from xtquant.xtconstant import (
        STOCK_BUY,
        STOCK_SELL,
        FIX_PRICE,
        LATEST_PRICE,
        MARKET_SH_CONFIRM,
        MARKET_SZ_CONFIRM,
    )

    _XTQUANT_AVAILABLE = True
except ImportError:
    logger.debug("xtquant not available – Galaxy QMT broker will use simulation mode")


class GalaxyQMTBroker(BrokerInterface):
    """Galaxy Securities QMT trading interface.

    Connects to a locally running QMT terminal (MiniQMT or full QMT)
    and provides programmatic order execution and account queries.

    Two modes:
        - Live: Requires QMT terminal running locally with xtquant installed.
        - Simulation: Falls back to simulated execution when xtquant is absent
          (useful for testing strategy logic without a live account).

    Config options (from config/broker.yaml):
        qmt_path: Path to QMT userdata_mini directory.
        session_id: QMT session ID (default: 123456).
        account_id: Broker account number.
    """

    name = "galaxy_qmt"

    def __init__(
        self,
        credential_manager=None,
        config: dict = None,
    ):
        self._config = config or {}
        self._cred = credential_manager
        self._trader = None
        self._account = None
        self._connected = False
        self._simulated = not _XTQUANT_AVAILABLE

        qmt_cfg = self._config.get("galaxy_qmt", {})
        self._qmt_path = qmt_cfg.get("qmt_path", "")
        self._session_id = qmt_cfg.get("session_id", 123456)
        self._account_id = qmt_cfg.get("account_id", "")

        if self._simulated:
            logger.info("GalaxyQMTBroker initialised in SIMULATION mode (xtquant not installed)")

    # -- Connection ---------------------------------------------------------

    def connect(self, **credentials) -> bool:
        """Connect to QMT terminal.

        Credentials are loaded from CredentialManager if available,
        or passed directly via kwargs.
        """
        # Load credentials
        username = credentials.get("username")
        password = credentials.get("password")

        if not username and self._cred:
            creds = self._cred.get_broker_credentials("galaxy")
            if creds:
                username = creds.get("username")
                password = creds.get("password")

        if self._simulated:
            logger.info("QMT broker connected (simulation mode)")
            self._connected = True
            self._account = AccountInfo(
                account_id=self._account_id or "sim_account",
                total_asset=1_000_000.0,
                available_cash=1_000_000.0,
            )
            return True

        # Live connection via xtquant
        try:
            session = int(self._session_id)
            qmt_path = self._qmt_path or self._find_qmt_path()

            if not qmt_path:
                logger.error("QMT path not configured. Set qmt_path in config/broker.yaml")
                return False

            self._trader = xttrader.XtQuantTrader(qmt_path, session)
            self._account = StockAccount(self._account_id, "STOCK")
            self._trader.start()
            self._connected = True

            logger.info(f"Connected to QMT at {qmt_path} (session {session})")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to QMT: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from QMT terminal."""
        self._connected = False
        if self._trader:
            try:
                self._trader.stop()
            except Exception:
                pass
            self._trader = None
        logger.info("Disconnected from QMT")

    def is_connected(self) -> bool:
        return self._connected

    def _find_qmt_path(self) -> str:
        """Attempt to auto-detect QMT userdata_mini path."""
        candidates = [
            r"C:\Program Files\Galaxy\QMT\userdata_mini",
            r"D:\QMT\userdata_mini",
            os.path.expanduser("~/QMT/userdata_mini"),
        ]
        for path in candidates:
            if Path(path).exists():
                return path
        return ""

    # -- Account ------------------------------------------------------------

    def get_account(self) -> Optional[AccountInfo]:
        if not self._connected:
            return None

        if self._simulated:
            return self._account

        try:
            asset = self._trader.query_stock_asset(self._account)
            if asset:
                return AccountInfo(
                    account_id=self._account_id,
                    total_asset=asset.total_asset,
                    available_cash=asset.cash,
                    frozen_cash=asset.frozen_cash,
                    market_value=asset.market_value,
                )
        except Exception as e:
            logger.error(f"Failed to query account: {e}")
        return None

    # -- Positions ----------------------------------------------------------

    def get_positions(self) -> list[Position]:
        if not self._connected:
            return []

        if self._simulated:
            return self._sim_positions

        try:
            raw = self._trader.query_stock_position(self._account)
            positions = []
            for p in (raw or []):
                positions.append(Position(
                    symbol=p.stock_code,
                    name=getattr(p, "stock_name", ""),
                    quantity=p.volume,
                    available=p.can_use_volume,
                    avg_cost=p.open_price,
                    current_price=p.market_value / p.volume if p.volume else 0,
                    market_value=p.market_value,
                ))
            return positions
        except Exception as e:
            logger.error(f"Failed to query positions: {e}")
            return []

    _sim_positions: list[Position] = []

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
                message="Not connected to broker",
            )

        # Validate lot size (A-shares: 100-share lots)
        if quantity % 100 != 0:
            return OrderResult(
                order_id="", symbol=symbol, side=side, quantity=quantity,
                price=price, status=OrderStatus.REJECTED,
                message="A-share order quantity must be a multiple of 100",
            )

        if self._simulated:
            import uuid

            order_id = str(uuid.uuid4())[:8]
            result = OrderResult(
                order_id=order_id, symbol=symbol, side=side,
                quantity=quantity, price=price,
                status=OrderStatus.FILLED,
                filled_quantity=quantity, filled_price=price or 100.0,
                message="[SIMULATED] Order filled",
            )

            # Update simulated positions
            if side == OrderSide.BUY:
                cost = (price or 100.0) * quantity
                if self._account:
                    self._account.available_cash -= cost
                    self._account.market_value += cost
            else:
                cost = (price or 100.0) * quantity
                if self._account:
                    self._account.available_cash += cost
                    self._account.market_value -= cost

            logger.info(f"[SIM] {side.value.upper()} {quantity} {symbol} @ {price or 'MKT'}")
            return result

        # Live order via xtquant
        try:
            xt_side = STOCK_BUY if side == OrderSide.BUY else STOCK_SELL
            xt_price_type = FIX_PRICE if order_type == OrderType.LIMIT else LATEST_PRICE

            order_id = self._trader.order_stock(
                self._account, symbol, xt_side, quantity,
                xt_price_type, price, "quantsys", "",
            )

            logger.info(f"Order submitted: {order_id} {side.value} {quantity} {symbol} @ {price}")

            return OrderResult(
                order_id=str(order_id) if order_id else "",
                symbol=symbol, side=side, quantity=quantity,
                price=price, status=OrderStatus.SUBMITTED,
                message=f"Order ID: {order_id}",
            )

        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResult(
                order_id="", symbol=symbol, side=side, quantity=quantity,
                price=price, status=OrderStatus.REJECTED,
                message=str(e),
            )

    def cancel_order(self, order_id: str) -> bool:
        if not self._connected:
            return False

        if self._simulated:
            logger.info(f"[SIM] Cancelled order {order_id}")
            return True

        try:
            self._trader.cancel_order_stock(self._account, order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_orders(self, status: OrderStatus = None) -> list[OrderResult]:
        if not self._connected:
            return []

        if self._simulated:
            return []

        try:
            orders = self._trader.query_stock_orders(self._account)
            results = []
            for o in (orders or []):
                results.append(OrderResult(
                    order_id=str(o.order_id),
                    symbol=o.stock_code,
                    side=OrderSide.BUY if o.order_type == STOCK_BUY else OrderSide.SELL,
                    quantity=o.order_volume,
                    price=o.price,
                    status=OrderStatus.SUBMITTED if o.order_status == 0 else OrderStatus.FILLED,
                    filled_quantity=o.traded_volume,
                    filled_price=o.traded_price,
                ))
            return results
        except Exception as e:
            logger.error(f"Failed to query orders: {e}")
            return []
