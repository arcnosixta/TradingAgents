"""FastAPI application for TradingAgents web dashboard + landing."""

import datetime
import json
import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.scanner import REPORT_NAMES, REPORT_ORDER, RunInfo, get_run, scan_runs
from web.runner import RunManager

PROJECT_ROOT = Path(__file__).parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"

app = FastAPI(title="TradingAgents")

# Mount static files for existing dashboard
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount landing static files
landing_dir = PROJECT_ROOT / "landing"
if landing_dir.exists():
    app.mount("/landing", StaticFiles(directory=str(landing_dir)), name="landing")

# Templates
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Runner
runner = RunManager(str(PROJECT_ROOT))


# ── Landing page ──
@app.get("/", response_class=HTMLResponse)
async def landing():
    landing_html = landing_dir / "index.html"
    if landing_html.exists():
        return FileResponse(str(landing_html))
    return RedirectResponse("/dashboard")


# ── Dashboard (moved from /) ──
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    runs = scan_runs(str(RUNS_DIR))
    running = runner.get_status()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "runs": runs,
            "running": running,
            "now": datetime.datetime.now().strftime("%Y-%m-%d"),
        },
    )


@app.get("/report/{run_id}", response_class=HTMLResponse)
async def report(request: Request, run_id: str):
    run = get_run(str(RUNS_DIR), run_id)
    if not run:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "run": run,
            "report_names": REPORT_NAMES,
            "report_order": REPORT_ORDER,
        },
    )


@app.post("/api/runs/start")
async def start_run(ticker: str = Form(...), trade_date: str = Form(...)):
    try:
        state = runner.start(ticker, trade_date)
        return {"status": "started", "ticker": ticker, "date": trade_date}
    except RuntimeError as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/runs/{run_id}/progress")
async def run_progress(run_id: str):
    run = get_run(str(RUNS_DIR), run_id)
    if not run:
        return {"status": "not_found"}
    return {
        "status": run.status,
        "agents_done": run.agents_completed,
        "agents_total": run.agents_total,
        "elapsed": run.elapsed_display,
    }


@app.get("/api/status")
async def current_status():
    state = runner.get_status()
    if not state:
        return {"status": "idle"}
    return {
        "status": state.status,
        "ticker": state.ticker,
        "date": state.date,
        "agents_done": state.agents_done,
        "agents_total": state.agents_total,
        "elapsed": round(state.elapsed, 1),
    }
