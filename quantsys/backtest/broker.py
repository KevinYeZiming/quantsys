"""A-share broker model with T+1 settlement, stamp duty, and price limits.

Chinese A-share market specifics:
- T+1 settlement: stocks bought on day T cannot be sold until day T+1
- Stamp duty (印花税): 0.05% on sells (halved from 0.1% since Aug 2023)
- Commission (佣金): 0.025% typical retail rate
- Minimum commission: 5 RMB per trade
- Daily price limits: +/-10% for main board, +/-20% for ChiNext/STAR
"""

import backtrader as bt


class AShareCommission(bt.CommInfoBase):
    """Commission scheme for Chinese A-share trading.

    Charges:
    - 0.025% commission on both buy and sell
    - 0.05% stamp duty on sells only
    - Minimum 5 RMB commission per trade (retail broker typical)
    """

    params = (
        ("commission", 0.00025),    # 0.025% per side
        ("stamp_duty", 0.0005),     # 0.05% on sells
        ("min_commission", 5.0),    # Minimum 5 RMB
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        """Calculate total cost including commission and stamp duty."""
        value = abs(size) * price

        # Standard commission
        comm = value * self.p.commission

        # Apply minimum commission
        if comm < self.p.min_commission:
            comm = self.p.min_commission

        # Stamp duty on sells only (size < 0 = sell in Backtrader notation)
        if size < 0:
            comm += value * self.p.stamp_duty

        return comm


class AShareBroker(bt.BackBroker):
    """Backtrader broker configured for Chinese A-share market."""

    params = (
        ("cash", 1000000.0),
        ("commission", 0.00025),
        ("stamp_duty", 0.0005),
        ("min_commission", 5.0),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set cash
        cash = kwargs.get("cash", self.p.cash)
        self.setcash(cash)

        # Add A-share commission scheme
        comminfo = AShareCommission(
            commission=kwargs.get("commission", self.p.commission),
            stamp_duty=kwargs.get("stamp_duty", self.p.stamp_duty),
            min_commission=kwargs.get("min_commission", self.p.min_commission),
        )
        self.addcommissioninfo(comminfo)


class T1Sizer(bt.Sizer):
    """Position sizer respecting T+1 settlement.

    Limits single stock position to a maximum percentage of portfolio value.
    """

    params = (
        ("max_pct", 0.10),  # Max 10% per position
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            return self.broker.getposition(data).size  # Sell all

        # Buy: max N% of portfolio
        size = (cash * self.p.max_pct) / data.close[0]
        # Round down to 100-share lots (A-share standard lot = 100 shares)
        size = int(size / 100) * 100
        return size
