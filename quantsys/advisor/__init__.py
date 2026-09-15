"""Quantitative evaluation advisor for live trading assistance.

Provides stock scoring, portfolio health diagnostics, portfolio
optimization, and trade recommendations — designed for
human-in-the-loop decision making. Never auto-executes trades.
"""

from quantsys.advisor.evaluator import StockEvaluator, EvalResult, Action as EvalAction
from quantsys.advisor.recommendation import RecommendationEngine, TradeSignal, DailyBriefing, StrategyMode, SignalType
from quantsys.advisor.portfolio_health import PortfolioHealthChecker, HealthReport
from quantsys.advisor.portfolio_evaluator import PortfolioEvaluator, PortfolioReport
from quantsys.advisor.position_tracker import PositionTracker, PortfolioSnapshot, Position
from quantsys.advisor.index_analyzer import IndexAnalyzer, IndexSnapshot, IndexDashboard

__all__ = [
    "StockEvaluator", "EvalResult", "EvalAction",
    "RecommendationEngine", "TradeSignal", "DailyBriefing",
    "StrategyMode", "SignalType",
    "PortfolioHealthChecker", "HealthReport",
    "PortfolioEvaluator", "PortfolioReport",
    "PositionTracker", "PortfolioSnapshot", "Position",
    "IndexAnalyzer", "IndexSnapshot", "IndexDashboard",
]
