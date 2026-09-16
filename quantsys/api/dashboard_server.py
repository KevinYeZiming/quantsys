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
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent.parent.parent
DASHBOARD_JSON = PROJECT_ROOT / "dashboard" / "dist" / "data" / "dashboard.json"
DIST_DIR = PROJECT_ROOT / "dashboard" / "dist"
POSITIONS_FILE = PROJECT_ROOT / "data" / "positions.json"

VALID_ASSET_TYPES = {"stock": "股票", "etf": "ETF", "fund": "场外基金", "gold": "黄金"}

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
    allow_methods=["GET", "POST"],
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
_abort = False
_last_heartbeat = 0.0
_current_proc: "asyncio.subprocess.Process | None" = None
_watchdog_started = False

HEARTBEAT_TIMEOUT = 90  # 秒。需大于浏览器后台标签页的激进定时器节流（约 60 秒）


async def _watchdog():
    """前端心跳看门狗：页面关闭/休眠后自动终止更新，杜绝孤儿进程。

    更新进行中前端每 10 秒 POST /api/heartbeat；超过 HEARTBEAT_TIMEOUT 秒
    未收到心跳，说明页面已失联（关闭、合盖休眠、网络断开），杀掉子进程并复位。
    """
    global _abort
    while True:
        await asyncio.sleep(10)
        if _running and time.monotonic() - _last_heartbeat > HEARTBEAT_TIMEOUT:
            proc = _current_proc
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            _abort = True


@app.post("/api/heartbeat")
def api_heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.monotonic()
    return {"ok": True}


@app.post("/api/bye")
def api_bye():
    """页面关闭时前端 sendBeacon 调用：将心跳回拨 60 秒。

    若有其他标签页仍在发送心跳，下一次心跳会覆盖此值，不会误杀；
    否则看门狗将在 30 秒内（HEARTBEAT_TIMEOUT=90）清理更新。
    """
    global _last_heartbeat
    _last_heartbeat = min(_last_heartbeat, time.monotonic() - 60)
    return {"ok": True}


def _validate_positions(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise HTTPException(400, "持仓数据必须是数组")
    cleaned, seen = [], set()
    for i, p in enumerate(payload):
        if not isinstance(p, dict):
            raise HTTPException(400, f"第 {i + 1} 条持仓格式错误")
        symbol = str(p.get("symbol", "")).strip()
        if not (len(symbol) == 6 and symbol.isdigit()):
            raise HTTPException(400, f"第 {i + 1} 条：代码必须是 6 位数字，当前为「{symbol}」")
        if symbol in seen:
            raise HTTPException(400, f"代码 {symbol} 重复")
        seen.add(symbol)
        asset_type = str(p.get("asset_type", "")).strip()
        if asset_type not in VALID_ASSET_TYPES:
            raise HTTPException(400, f"{symbol}：类型必须是 {list(VALID_ASSET_TYPES)} 之一")
        try:
            quantity = float(p.get("quantity"))
            avg_cost = float(p.get("avg_cost"))
        except (TypeError, ValueError):
            raise HTTPException(400, f"{symbol}：数量与成本必须是数字")
        if quantity <= 0 or avg_cost <= 0:
            raise HTTPException(400, f"{symbol}：数量与成本必须大于 0")
        cleaned.append({
            "symbol": symbol,
            "name": str(p.get("name", symbol)).strip() or symbol,
            "asset_type": asset_type,
            "quantity": quantity,
            "avg_cost": avg_cost,
            "added_date": str(p.get("added_date", "")).strip() or time.strftime("%Y-%m-%d"),
        })
    return cleaned


@app.get("/api/positions")
def api_get_positions():
    if POSITIONS_FILE.exists():
        return json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
    return []


@app.post("/api/positions")
async def api_save_positions(request: Request):
    global _running
    if _running:
        raise HTTPException(409, "更新进行中，请等待完成后再编辑持仓")
    positions = _validate_positions(await request.json())
    tmp = POSITIONS_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(POSITIONS_FILE)
    # 重新导出 dashboard.json，让页面立即反映持仓变化
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "scripts/export_dashboard_data.py",
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
    return {"ok": True, "count": len(positions), "exported": proc.returncode == 0}


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
        global _running, _abort, _last_heartbeat, _watchdog_started, _current_proc
        if _running:
            yield "event: error\ndata: {\"message\": \"更新正在进行中，请等待完成\"}\n\n"
            return
        _running = True
        _abort = False
        _last_heartbeat = time.monotonic()
        if not _watchdog_started:
            _watchdog_started = True
            asyncio.create_task(_watchdog())
        proc = None  # 当前子进程，断开时务必杀掉，避免孤儿进程

        async def kill_child():
            nonlocal proc
            global _current_proc
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except (ProcessLookupError, asyncio.CancelledError):
                    pass
            proc = None
            _current_proc = None

        try:
            for step in _build_pipeline():
                if _abort:
                    yield (
                        "event: error\ndata: "
                        + json.dumps({"message": "页面连接中断，更新已终止"}, ensure_ascii=False)
                        + "\n\n"
                    )
                    return
                payload = {"id": step["id"], "label": step["label"], "status": "running"}
                yield f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                proc = await asyncio.create_subprocess_exec(
                    *step["cmd"],
                    cwd=str(PROJECT_ROOT),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                _current_proc = proc
                log_lines: list[str] = []
                deadline = time.monotonic() + 1800
                timed_out = False
                aborted = False
                assert proc.stdout is not None
                while True:
                    if _abort:
                        aborted = True
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    try:
                        line = await asyncio.wait_for(
                            proc.stdout.readline(), timeout=min(remaining, 5.0)
                        )
                    except asyncio.TimeoutError:
                        # 无输出期间发送 SSE 注释作心跳：若写入失败（客户端已断开）
                        # 异常会向上传播并触发 CancelledError 清理逻辑
                        yield ": ping\n\n"
                        if proc.returncode is not None:
                            break
                        continue
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").rstrip()
                    if not text:
                        continue
                    log_lines.append(text)
                    # 实时推送子进程输出，前端逐步显示进度
                    yield (
                        "event: log\ndata: "
                        + json.dumps({"id": step["id"], "line": text}, ensure_ascii=False)
                        + "\n\n"
                    )
                if aborted:
                    # 页面失联，看门狗已杀子进程：告知前端并结束整条流水线
                    yield (
                        "event: error\ndata: "
                        + json.dumps({"message": "页面连接中断，更新已终止"}, ensure_ascii=False)
                        + "\n\n"
                    )
                    return
                if timed_out:
                    await kill_child()
                    code, note = -1, "超时（30 分钟）"
                else:
                    await proc.wait()
                    code = proc.returncode
                    note = "成功" if code == 0 else f"退出码 {code}"
                proc = None
                _current_proc = None
                payload = {
                    "id": step["id"], "label": step["label"],
                    "status": "ok" if code == 0 else "failed",
                    "returncode": code, "note": note,
                    "log_tail": log_lines[-5:],
                }
                yield f"event: step\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except asyncio.CancelledError:
            # 客户端断开（关页面/合盖休眠）：立即终止子进程并复位状态
            await kill_child()
            raise
        finally:
            _running = False
            _current_proc = None

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
