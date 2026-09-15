"""FastAPI REST backend for quantsys data management and trading.

Provides HTTP endpoints for:
- Data update and freshness monitoring
- Factor calculation and retrieval
- Strategy backtest execution
- Trading signal generation
- Broker connection and order management
- Credential management

Usage::

    uvicorn quantsys.api.server:app --host 0.0.0.0 --port 8888
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# -- Detect project root -----------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# -- Lazy imports (avoid heavy imports at module level) ----------------
_fastapi_imports_done = False


def _ensure_imports():
    global _fastapi_imports_done, FastAPI, HTTPException, CORSMiddleware
    global JSONResponse, BackgroundTasks
    if not _fastapi_imports_done:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi import BackgroundTasks

        _fastapi_imports_done = True


# -- App factory ------------------------------------------------------


def create_app() -> "FastAPI":
    """Create and configure the FastAPI application."""
    _ensure_imports()

    app = FastAPI(
        title="Quantsys API",
        description="中国A股量化交易系统 - Data Management & Trading API",
        version="0.2.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routes(app)
    return app


# -- State helpers -----------------------------------------------------


class _AppState:
    """Lazy-loaded application state shared across requests."""

    def __init__(self):
        self._cache = None
        self._calendar = None
        self._universe_builder = None
        self._cred_manager = None
        self._broker = None
        self._strategy = None
        self._configs = None

    @property
    def cache(self):
        if self._cache is None:
            from quantsys.data.sources.cache import CacheManager
            self._cache = CacheManager(_PROJECT_ROOT / "data" / "raw")
        return self._cache

    @property
    def calendar(self):
        if self._calendar is None:
            from quantsys.data.calendar import TradingCalendar
            self._calendar = TradingCalendar(self.cache)
        return self._calendar

    @property
    def universe_builder(self):
        if self._universe_builder is None:
            from quantsys.data.universe import UniverseBuilder
            self._universe_builder = UniverseBuilder(self.cache)
        return self._universe_builder

    @property
    def cred_manager(self):
        if self._cred_manager is None:
            from quantsys.security.credential import CredentialManager
            self._cred_manager = CredentialManager(_PROJECT_ROOT)
        return self._cred_manager

    @property
    def configs(self):
        if self._configs is None:
            from quantsys.utils.config import load_all_configs
            self._configs = load_all_configs(_PROJECT_ROOT / "config")
        return self._configs

    @property
    def broker(self):
        if self._broker is None:
            broker_cfg = self.configs.get("broker", {})
            try:
                from quantsys.broker.galaxy_qmt import GalaxyQMTBroker
                self._broker = GalaxyQMTBroker(
                    credential_manager=self.cred_manager,
                    config=broker_cfg,
                )
            except ImportError:
                from quantsys.broker.simulated import SimulatedBroker
                self._broker = SimulatedBroker()
        return self._broker

    def reset_strategy(self):
        self._strategy = None

    def get_strategy(self, strategy_name: str = "multifactor"):
        if self._strategy is None:
            from quantsys.strategies.multifactor import MultiFactorStrategy
            from quantsys.strategies.etf_rotation import ETFRotationStrategy
            from quantsys.strategies.trend_following import TrendFollowingStrategy
            from quantsys.strategies.industry_rotation import IndustryRotationStrategy

            strategy_map = {
                "multifactor": MultiFactorStrategy,
                "etf_rotation": ETFRotationStrategy,
                "trend_following": TrendFollowingStrategy,
                "industry_rotation": IndustryRotationStrategy,
            }
            strategy_cls = strategy_map.get(strategy_name, MultiFactorStrategy)
            strategy_config = self.configs.get("strategies", {})
            self._strategy = strategy_cls(
                config=strategy_config,
                cache_dir=str(_PROJECT_ROOT / "data" / "raw"),
            )
        return self._strategy


_state = _AppState()

# -- In-memory task tracking -------------------------------------------
_backtest_tasks: dict[str, dict] = {}


# =====================================================================
# Routes
# =====================================================================

def _register_routes(app: "FastAPI"):

    # -- Health --------------------------------------------------------

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.2.0",
            "timestamp": datetime.now().isoformat(),
        }

    # -- Data ----------------------------------------------------------

    @app.get("/api/data/status")
    async def data_status():
        """Check data freshness for all data types."""
        cache = _state.cache
        raw_dir = cache.cache_dir

        status = {}
        for dtype in ["stock_daily", "index_daily", "etf_daily", "trade_calendar",
                       "financials", "macro"]:
            d = raw_dir / dtype
            status[dtype] = {
                "exists": d.exists(),
                "file_count": len(list(d.glob("*.parquet"))) if d.exists() else 0,
            }

        # Check latest stock data date
        latest_date = None
        stock_dir = raw_dir / "stock_daily"
        if stock_dir.exists():
            for f in list(stock_dir.glob("*.parquet"))[:5]:
                try:
                    import pandas as pd
                    df = pd.read_parquet(f)
                    if not df.empty:
                        max_date = pd.Timestamp(df.index.max() if hasattr(df.index, 'max') else df["date"].max())
                        if latest_date is None or max_date > latest_date:
                            latest_date = max_date
                except Exception:
                    pass

        return {
            "data_types": status,
            "latest_date": str(latest_date.date()) if latest_date else None,
            "needs_update": latest_date is None or (
                datetime.now().date() - latest_date.date()).days > 1 if latest_date else True,
        }

    @app.post("/api/data/update")
    async def trigger_data_update(background_tasks: "BackgroundTasks"):
        """Trigger an incremental data update (runs in background)."""
        task_id = str(uuid.uuid4())[:8]

        def _update():
            import subprocess
            result = subprocess.run(
                [sys.executable, str(_PROJECT_ROOT / "scripts" / "update_data.py")],
                capture_output=True, text=True, timeout=600,
            )
            _backtest_tasks[task_id] = {
                "status": "completed" if result.returncode == 0 else "failed",
                "output": result.stdout[-2000:],
                "error": result.stderr[-1000:] if result.returncode != 0 else None,
            }

        background_tasks.add_task(_update)
        return {"task_id": task_id, "status": "started"}

    @app.get("/api/data/update/status/{task_id}")
    async def data_update_status(task_id: str):
        task = _backtest_tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    # -- Universe ------------------------------------------------------

    @app.get("/api/universe/{date}")
    async def get_universe(date: str, index_code: str = "000300"):
        """Get tradeable stock universe for a given date."""
        try:
            universe = _state.universe_builder.build(date, index_code=index_code)
            return {"date": date, "index": index_code, "count": len(universe), "symbols": universe}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # -- Factors -------------------------------------------------------

    @app.get("/api/factors/{date}")
    async def get_factors(date: str, symbols: str = None):
        """Get factor values for a date. Optionally filter by comma-separated symbols."""
        try:
            strategy = _state.get_strategy("multifactor")
            if symbols:
                universe = [s.strip() for s in symbols.split(",")]
            else:
                universe = _state.universe_builder.build(date)

            signals = strategy.generate_signals(universe, date)
            return {
                "date": date,
                "factor_count": 20,
                "stocks_with_signals": len(signals),
                "signals": signals.to_dict() if not signals.empty else {},
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # -- Backtest ------------------------------------------------------

    @app.post("/api/backtest/run")
    async def run_backtest(
        background_tasks: "BackgroundTasks",
        strategy_name: str = "multifactor",
        start: str = "2023-01-01",
        end: str = "2023-12-31",
        universe: str = "csi300",
    ):
        """Run a strategy backtest (runs in background)."""
        task_id = str(uuid.uuid4())[:8]
        _backtest_tasks[task_id] = {"status": "running", "progress": 0}

        def _run():
            import subprocess
            result = subprocess.run(
                [
                    sys.executable,
                    str(_PROJECT_ROOT / "scripts" / "run_backtest.py"),
                    "--strategy", strategy_name,
                    "--start", start,
                    "--end", end,
                    "--universe", universe,
                ],
                capture_output=True, text=True, timeout=600,
            )
            _backtest_tasks[task_id] = {
                "status": "completed" if result.returncode == 0 else "failed",
                "output": result.stdout[-3000:],
                "error": result.stderr[-1000:] if result.returncode != 0 else None,
            }

        background_tasks.add_task(_run)
        return {"task_id": task_id, "status": "started"}

    @app.get("/api/backtest/status/{task_id}")
    async def backtest_status(task_id: str):
        task = _backtest_tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    # -- Signals -------------------------------------------------------

    @app.get("/api/signals/{date}")
    async def get_signals(date: str, strategy_name: str = "multifactor"):
        """Generate trading signals for a date."""
        try:
            strategy = _state.get_strategy(strategy_name)
            universe = _state.universe_builder.build(date)
            signals = strategy.generate_signals(universe, date)

            if signals.empty:
                return {"date": date, "strategy": strategy_name, "signals": [], "count": 0}

            # Sort by weight descending
            sorted_signals = signals.sort_values(ascending=False)
            result = [
                {"symbol": s, "weight": round(w, 4)}
                for s, w in sorted_signals.items()
            ]
            return {
                "date": date,
                "strategy": strategy_name,
                "count": len(result),
                "signals": result,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # -- Broker --------------------------------------------------------

    @app.post("/api/broker/connect")
    async def broker_connect():
        """Connect to broker (QMT or simulated)."""
        try:
            success = _state.broker.connect()
            return {"connected": success, "broker": _state.broker.name}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/broker/disconnect")
    async def broker_disconnect():
        _state.broker.disconnect()
        return {"connected": False}

    @app.get("/api/broker/status")
    async def broker_status():
        return {
            "connected": _state.broker.is_connected(),
            "broker": _state.broker.name,
        }

    @app.get("/api/broker/account")
    async def broker_account():
        if not _state.broker.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to broker")
        account = _state.broker.get_account()
        if not account:
            raise HTTPException(status_code=500, detail="Failed to get account info")
        return {
            "account_id": account.account_id,
            "total_asset": account.total_asset,
            "available_cash": account.available_cash,
            "market_value": account.market_value,
            "total_return": account.total_return,
        }

    @app.get("/api/broker/positions")
    async def broker_positions():
        if not _state.broker.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to broker")
        positions = _state.broker.get_positions()
        return {
            "count": len(positions),
            "positions": [
                {
                    "symbol": p.symbol,
                    "name": p.name,
                    "quantity": p.quantity,
                    "available": p.available,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                    "market_value": p.market_value,
                    "profit_loss": p.profit_loss,
                    "profit_loss_pct": p.profit_loss_pct,
                }
                for p in positions
            ],
        }

    @app.post("/api/broker/order")
    async def broker_submit_order(
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "limit",
        price: float = 0.0,
    ):
        """Submit a trading order.

        Args:
            symbol: Stock code, e.g. '600519'.
            side: 'buy' or 'sell'.
            quantity: Number of shares (multiple of 100).
            order_type: 'limit' or 'market'.
            price: Limit price (required for limit orders).
        """
        if not _state.broker.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to broker")

        from quantsys.broker.base import OrderSide, OrderType

        try:
            os_side = OrderSide(side.lower())
            ot = OrderType(order_type.lower())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid side/type: {e}")

        if ot == OrderType.LIMIT and price <= 0:
            raise HTTPException(status_code=400, detail="Price required for limit orders")

        if quantity % 100 != 0:
            raise HTTPException(status_code=400, detail="Quantity must be multiple of 100")

        result = _state.broker.submit_order(symbol, os_side, quantity, ot, price)
        return {
            "order_id": result.order_id,
            "symbol": result.symbol,
            "side": result.side.value,
            "quantity": result.quantity,
            "price": result.price,
            "status": result.status.value,
            "message": result.message,
            "filled_quantity": result.filled_quantity,
        }

    @app.delete("/api/broker/order/{order_id}")
    async def broker_cancel_order(order_id: str):
        if not _state.broker.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to broker")
        success = _state.broker.cancel_order(order_id)
        return {"order_id": order_id, "cancelled": success}

    @app.get("/api/broker/orders")
    async def broker_orders():
        if not _state.broker.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to broker")
        orders = _state.broker.get_orders()
        return {
            "count": len(orders),
            "orders": [
                {"order_id": o.order_id, "symbol": o.symbol, "side": o.side.value,
                 "quantity": o.quantity, "price": o.price, "status": o.status.value,
                 "filled_quantity": o.filled_quantity}
                for o in orders
            ],
        }

    # -- Credentials ---------------------------------------------------

    @app.post("/api/credentials/set")
    async def credentials_set(
        broker: str, username: str, password: str, account_id: str = ""
    ):
        """Save encrypted broker credentials."""
        try:
            kwargs = {"account_id": account_id} if account_id else {}
            path = _state.cred_manager.save_broker_credentials(
                broker, username, password, **kwargs
            )
            return {"broker": broker, "saved": True, "path": str(path)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/credentials/status")
    async def credentials_status():
        """Check which brokers have stored credentials."""
        brokers = _state.cred_manager.list_brokers()
        return {"brokers_with_credentials": brokers, "count": len(brokers)}

    @app.delete("/api/credentials/{broker}")
    async def credentials_delete(broker: str):
        success = _state.cred_manager.delete_broker_credentials(broker)
        return {"broker": broker, "deleted": success}

    # -- System config -------------------------------------------------

    @app.get("/api/config")
    async def get_config():
        """Get current system configuration (safe, no credentials)."""
        configs = _state.configs
        return {
            "strategies": configs.get("strategies", {}),
            "backtest": configs.get("backtest", {}),
            "risk": configs.get("risk", {}),
            "broker": configs.get("broker", {}),
        }


# =====================================================================
# App instance
# =====================================================================

app = create_app()


def main():
    """Entry point for running the API server."""
    import uvicorn

    uvicorn.run(
        "quantsys.api.server:app",
        host="0.0.0.0",
        port=8888,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
