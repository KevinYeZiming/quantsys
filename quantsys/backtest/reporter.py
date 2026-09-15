"""HTML report generator for backtest results."""

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from quantsys.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)

# Chinese font configuration
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


class ReportGenerator:
    """Generate HTML performance reports from backtest results.

    Usage::

        result: BacktestResult = engine.run()
        report_path = ReportGenerator.generate(result, output_dir="reports/")
    """

    @staticmethod
    def generate(
        result: BacktestResult,
        output_dir: str | Path = "reports",
        filename: str = None,
    ) -> Path:
        """Generate an HTML backtest report with plots.

        Args:
            result: BacktestResult from engine.run().
            output_dir: Directory for output files.
            filename: Optional custom filename (without extension).

        Returns:
            Path to the generated HTML report.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            filename = f"backtest_{result.strategy_name}_{result.end_date[:10]}"

        # Generate plots
        plot_path = output_dir / f"{filename}.png"
        ReportGenerator._generate_plots(result, plot_path)

        # Generate HTML
        html_path = output_dir / f"{filename}.html"
        html_content = ReportGenerator._build_html(result, plot_path.name)
        html_path.write_text(html_content, encoding="utf-8")

        logger.info(f"Report generated: {html_path}")
        return html_path

    @staticmethod
    def _generate_plots(result: BacktestResult, output_path: Path):
        """Generate performance charts."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f"Backtest Report: {result.strategy_name}", fontsize=14, fontweight="bold")

        # 1. Equity curve
        ax1 = axes[0, 0]
        if not result.equity_curve.empty:
            ax1.plot(result.equity_curve.index, result.equity_curve.values,
                     label="Strategy", color="#1f77b4", linewidth=1)
        if not result.benchmark_returns.empty:
            benchmark_equity = (1 + result.benchmark_returns).cumprod() * 100
            ax1.plot(benchmark_equity.index, benchmark_equity.values,
                     label="Benchmark", color="#ff7f0e", linewidth=1, alpha=0.7)
        ax1.set_title("Equity Curve")
        ax1.set_ylabel("Portfolio Value")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. Drawdown
        ax2 = axes[0, 1]
        if not result.equity_curve.empty:
            equity = result.equity_curve
            running_max = equity.cummax()
            drawdown = (equity - running_max) / running_max * 100
            ax2.fill_between(drawdown.index, 0, drawdown.values, color="red", alpha=0.3)
            ax2.plot(drawdown.index, drawdown.values, color="red", linewidth=0.5)
        ax2.set_title("Drawdown")
        ax2.set_ylabel("Drawdown (%)")
        ax2.grid(True, alpha=0.3)

        # 3. Monthly returns heatmap
        ax3 = axes[1, 0]
        if not result.daily_returns.empty:
            monthly = result.daily_returns.resample("ME").apply(
                lambda x: (1 + x).prod() - 1
            ) * 100
            monthly.index = monthly.index.to_period("M")
            ax3.bar(range(len(monthly)), monthly.values, color=["green" if v > 0 else "red" for v in monthly.values], alpha=0.7)
            ax3.axhline(y=0, color="black", linewidth=0.5)
            if len(monthly) > 24:
                step = max(1, len(monthly) // 12)
                ax3.set_xticks(range(0, len(monthly), step))
                ax3.set_xticklabels([str(m) for m in monthly.index[::step]], rotation=45, ha="right")
        ax3.set_title("Monthly Returns (%)")
        ax3.grid(True, alpha=0.3)

        # 4. Metrics table
        ax4 = axes[1, 1]
        ax4.axis("off")
        metrics = result.to_dict()
        table_text = "\n".join([f"{k}: {v}" for k, v in metrics.items()])
        ax4.text(0.1, 0.9, table_text, transform=ax4.transAxes,
                 fontfamily="monospace", fontsize=10, verticalalignment="top")
        ax4.set_title("Performance Metrics")

        plt.tight_layout()
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    @staticmethod
    def _build_html(result: BacktestResult, plot_filename: str) -> str:
        """Build HTML report content."""
        metrics = result.to_dict()
        metrics_html = "\n".join(
            [f"<tr><td><b>{k}</b></td><td>{v}</td></tr>"
             for k, v in metrics.items()]
        )

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report: {result.strategy_name}</title>
    <style>
        body {{
            font-family: 'Arial Unicode MS', 'Segoe UI', sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        .metrics-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metrics-table td {{
            padding: 8px 15px;
            border-bottom: 1px solid #eee;
        }}
        .metrics-table tr:hover {{ background-color: #f8f9fa; }}
        .chart-container {{
            background: white;
            padding: 15px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .chart-container img {{
            width: 100%;
            height: auto;
        }}
        .footer {{
            text-align: center;
            color: #95a5a6;
            font-size: 12px;
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <h1>Backtest Report: {result.strategy_name}</h1>

    <p>Period: <b>{result.start_date}</b> to <b>{result.end_date}</b></p>

    <h2>Performance Metrics</h2>
    <table class="metrics-table">
        {metrics_html}
    </table>

    <h2>Performance Charts</h2>
    <div class="chart-container">
        <img src="{plot_filename}" alt="Performance Charts">
    </div>

    <div class="footer">
        Generated by 中国A股量化交易系统 | {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
    </div>
</body>
</html>"""
        return html
