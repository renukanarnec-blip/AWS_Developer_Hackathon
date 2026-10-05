"""StudyPilot: an MCP server (Streamable HTTP, spec 2025-11-25) for study planning.

Run:  uvicorn server:app --reload
MCP endpoint:  http://localhost:8000/mcp/
Simulator UI:  http://localhost:8000/
"""
import contextlib
import json
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from mcp.server.fastmcp import FastMCP

DB = Path(__file__).parent / "tasks.json"

mcp = FastMCP(
    "StudyPilot",
    instructions="Helps a student capture study tasks and plan their day.",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


def _load() -> list[dict]:
    return json.loads(DB.read_text()) if DB.exists() else []


def _save(tasks: list[dict]) -> None:
    DB.write_text(json.dumps(tasks, indent=2))


@mcp.tool()
def add_task(title: str, subject: str, due_date: str, est_minutes: int = 60) -> dict:
    """Add a study task. due_date must be YYYY-MM-DD; est_minutes is how long it should take."""
    datetime.strptime(due_date, "%Y-%m-%d")  # validates format
    task = {"id": uuid.uuid4().hex[:6], "title": title, "subject": subject,
            "due_date": due_date, "est_minutes": est_minutes, "done": False}
    tasks = _load()
    tasks.append(task)
    _save(tasks)
    return task


@mcp.tool()
def list_tasks(include_done: bool = False) -> list[dict]:
    """List study tasks, soonest due date first. Completed tasks are hidden unless include_done is true."""
    tasks = [t for t in _load() if include_done or not t["done"]]
    return sorted(tasks, key=lambda t: t["due_date"])


@mcp.tool()
def complete_task(task_id: str) -> dict:
    """Mark a task as done using its id."""
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = True
            _save(tasks)
            return t
    return {"error": f"No task with id {task_id}"}


@mcp.tool()
def plan_day(available_minutes: int = 120) -> dict:
    """Build today's study plan: fills the available time with the most urgent unfinished tasks."""
    today = date.today().isoformat()
    pending = sorted((t for t in _load() if not t["done"]), key=lambda t: t["due_date"])
    plan, used = [], 0
    for t in pending:
        if used + t["est_minutes"] <= available_minutes:
            plan.append({**t, "overdue": t["due_date"] < today})
            used += t["est_minutes"]
    skipped = [t["title"] for t in pending if t["id"] not in {p["id"] for p in plan}]
    return {"date": today, "minutes_planned": used, "plan": plan, "not_fitting_today": skipped}


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="StudyPilot", lifespan=lifespan)
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def simulator():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
