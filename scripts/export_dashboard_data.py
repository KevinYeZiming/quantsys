#!/usr/bin/env python3
"""Export system outputs to the dashboard's bundled data file.

Reads factor evaluation reports and the latest asset evaluations from
the local data cache and writes a single JSON that the React dashboard
imports at build time. Re-run after any evaluation to refresh the UI:

    python3 scripts/export_dashboard_data.py

Output: dashboard/src/data/dashboard.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
DASHBOARD_DATA = PROJECT_ROOT / "dashboard" / "src" / "data" / "dashboard.json"


def clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 6)
    if isinstance(v, np.ndarray):
        return [clean(x) for x in v.tolist()]
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def load_factor_summary():
    path = PROJECT_ROOT / "reports" / "factor_evaluation_summary.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    records = []
    for _, row in df.iterrows():
        records.append({k: clean(v) for k, v in row.items()})
    return records


def load_factor_details():
    path = PROJECT_ROOT / "reports" / "factor_details.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_correlation():
    path = PROJECT_ROOT / "reports" / "factor_correlation.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0)
    # Keep order consistent with factor summary ranking (drop all-NaN rows/cols)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return {
        "labels": list(df.index),
        "values": [[clean(v) for v in row] for row in df.values.tolist()],
    }


def load_latest_evaluations():
    eval_dir = PROJECT_ROOT / "data" / "evaluations"
    parquets = sorted(eval_dir.glob("eval_*.parquet")) if eval_dir.exists() else []
    if not parquets:
        return []
    df = pd.read_parquet(parquets[-1])
    records = []
    for _, row in df.iterrows():
        records.append({k: clean(v) for k, v in row.items()})
    return records


def load_positions():
    path = PROJECT_ROOT / "data" / "positions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    data = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "factor_summary": load_factor_summary(),
        "factor_details": load_factor_details(),
        "factor_correlation": load_correlation(),
        "evaluations": load_latest_evaluations(),
        "positions": load_positions(),
    }
    DASHBOARD_DATA.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = DASHBOARD_DATA.stat().st_size / 1024
    print(f"Dashboard data written: {DASHBOARD_DATA} "
          f"({size_kb:.0f} KB, {len(data['factor_summary'])} factors, "
          f"{len(data['evaluations'])} evaluations, "
          f"{len(data['positions'])} positions)")


if __name__ == "__main__":
    main()
