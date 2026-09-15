"""FastAPI server for the Quantsys dashboard: static hosting + one-click update.

Serves the built React dashboard (dashboard/dist) and exposes a small API:

- GET  /api/status   -> freshness info about the exported dashboard data
- GET  /api/update   -> SSE stream that runs the full update pipeline step by
                        step, emitting progress events for the frontend

Usage::

    python3 scripts/serve_dashboard.py
    # then open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent.parent.parent
DASHBOARD_JSON = PROJECT_ROOT / "dashboard" / "dist" / "data" / "dashboard.json"
DIST_DIR = PROJECT_ROOT / "dashboard" / "dist"

app = FastAPI(title="Quantsys Dashboard Server", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _cached_symbols() -> list[str]:
    """Symbols already present in the local parquet cache."""
    cache = PROJECT_ROOT / "data" / "raw" / "stock_daily"
    if not cache.exists():
        return []
    return sorted(p.stem for p in cache.glob("*.parquet"))


def _build_pipeline() -> list[dict]:
    symbols = ",".join(_cached_symbols())
    steps = [
        {
            "id": "stocks",
            "label": "更新股票行情",
            "cmd": [sys.executable, "scripts/update_data.py"],
        },
        {"id": "funds", "label": "更新基金数据",
         "cmd": [sys.executable, "scripts/update_assets.py", "--type", "fund"]},
        {"id": "gold", "label": "更新黄金数据",
         "cmd": [sys.executable, "scripts/update_assets.py", "--type", "gold"]},
        {"id": "factors", "label": "评估选股因子",
         "cmd": [sys.executable, "scripts/evaluate_factors.py",
                 "--start", "2022-01-01", "--save-weights",
                 "--min-cross-section", "10"]},
        {"id": "signals", "label": "生成买卖信号",
         "cmd": [sys.executable, "scripts/evaluate_assets.py", "--positions"]},
        {"id": "export", "label": "导出仪表盘数据",
         "cmd": [sys.executable, "scripts/export_dashboard_data.py"]},
    ]
    if symbols:
        steps[0]["cmd"] += ["--symbols", symbols]
    return steps


_running = False


@app.get("/api/status")
def api_status():
    info = {"dashboard_json": DASHBOARD_JSON.exists(), "generated_at": None}
    if DASHBOARD_JSON.exists():
        try:
            data = json.loads(DASHBOARD_JSON.read_text(encoding="utf-8"))
            info["generated_at"] = data.get("generated_at")
        except Exception:
            info["dashboard_json"] = False
    info["updating"] = _running
    return info


@app.get("/api/update")
def api_update():
    async def event_stream():
        global _running
        if _running:
            yield "event: error\ndata: {\"message\": \"更新正在进行中，请等待完成\"}\n\n"
            return
        _running = True
        try:
            for step in _build_pipeline():
                payload = {"id": step["id"], "label": step["label"], "status": "running"}
                yield f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                proc = await asyncio.create_subprocess_exec(
                    *step["cmd"],
                    cwd=str(PROJECT_ROOT),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1800)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    stdout = b""
                    code, note = -1, "超时（30 分钟）"
                else:
                    code = proc.returncode
                    note = "成功" if code == 0 else f"退出码 {code}"
                tail = stdout.decode("utf-8", errors="replace").strip().splitlines()[-5:]
                payload = {
                    "id": step["id"], "label": step["label"],
                    "status": "ok" if code == 0 else "failed",
                    "returncode": code, "note": note, "log_tail": tail,
                }
                yield f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            _running = False

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="dashboard")
else:
    @app.get("/")
    def no_build():
        return FileResponse(
            __file__,
            status_code=503,
            filename="build-missing.txt",
            content_disposition_type="inline",
        )
