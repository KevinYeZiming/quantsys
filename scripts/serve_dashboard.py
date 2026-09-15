#!/usr/bin/env python3
"""Start the Quantsys dashboard server (static UI + one-click update API).

Prerequisite: the frontend must be built once (or after UI code changes):

    cd dashboard && npm install && npm run build

Then run from the project root:

    python3 scripts/serve_dashboard.py

Open http://localhost:8000 — the page has a 一键更新 button that re-runs the
data pipeline and refreshes the numbers without a rebuild.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "quantsys.api.dashboard_server:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
