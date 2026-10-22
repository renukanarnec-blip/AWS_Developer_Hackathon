"""StudyPilot tools: an MCP server (Streamable HTTP, spec 2025-11-25) for study planning.

Run:  uvicorn server:app --reload
MCP endpoint:  http://localhost:8000/mcp/
Simulator UI:  http://localhost:8000/
"""
import asyncio
import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from llm import MODEL_ID, extract_tasks_sync

DB = Path(__file__).parent / "tasks.json"
PREFS = Path(__file__).parent / "prefs.json"

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


def _find(tasks: list[dict], ref: str) -> list[dict]:
    """Match a task by exact id, or by part of its title (case-insensitive)."""
    ref = (ref or "").strip().lower()
    exact = [t for t in tasks if t["id"] == ref]
    if exact or not ref:
        return exact
    return [t for t in tasks if ref in t["title"].lower()]


def _pick(tasks: list[dict], ref: str):
    """Return (task, error). Error explains no match or several matches."""
    hits = _find(tasks, ref)
    if not hits:
        return None, {"error": f"No task matches '{ref}'. Use list_tasks to see the tasks."}
    if len(hits) > 1:
        return None, {"error": "Several tasks match: " + "; ".join(f"{t['title']} [{t['id']}]" for t in hits)
                                + ". Ask the student which one, or use the id."}
    return hits[0], None


def _prefs() -> dict:
    """Saved study preferences, with defaults."""
    p = {"daily_minutes": 120, "preferred_time": None}
    if PREFS.exists():
        p.update(json.loads(PREFS.read_text()))
    return p


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
    """Mark a task as done. task_id can be the task's id or its title (or part of the title)."""
    tasks = _load()
    t, err = _pick(tasks, task_id)
    if err:
        return err
    t["done"] = True
    _save(tasks)
    return t


@mcp.tool()
def plan_day(available_minutes: int | None = None) -> dict:
    """Build today's study plan: fills the available time with the most urgent unfinished tasks.
    If available_minutes is not given, the student's saved daily goal is used."""
    available_minutes = available_minutes or _prefs()["daily_minutes"]
    today = date.today().isoformat()
    pending = sorted((t for t in _load() if not t["done"]), key=lambda t: t["due_date"])
    plan, used = [], 0
    for t in pending:
        if used + t["est_minutes"] <= available_minutes:
            plan.append({**t, "overdue": t["due_date"] < today})
            used += t["est_minutes"]
    skipped = [t["title"] for t in pending if t["id"] not in {p["id"] for p in plan}]
    return {"date": today, "minutes_planned": used, "plan": plan, "not_fitting_today": skipped,
            "preferred_time": _prefs()["preferred_time"]}


@mcp.tool()
def update_task(task_id: str, title: str | None = None, due_date: str | None = None,
                est_minutes: int | None = None) -> dict:
    """Change a task's title, due date (YYYY-MM-DD) or estimated minutes. task_id can be the id or the
    task's current title (or part of it). Only the fields given are changed."""
    tasks = _load()
    t, err = _pick(tasks, task_id)
    if err:
        return err
    if due_date:
        datetime.strptime(due_date, "%Y-%m-%d")
        t["due_date"] = due_date
    if title:
        t["title"] = title
    if est_minutes:
        t["est_minutes"] = est_minutes
    _save(tasks)
    return t


@mcp.tool()
def delete_task(task_id: str) -> dict:
    """Permanently delete a task. task_id can be the task's id or its title (or part of the title)."""
    tasks = _load()
    t, err = _pick(tasks, task_id)
    if err:
        return err
    _save([x for x in tasks if x["id"] != t["id"]])
    return {"deleted": t["title"]}


@mcp.tool()
def reschedule_overdue(daily_minutes: int | None = None) -> dict:
    """Catch-up plan: move every overdue, unfinished task to a new due date, starting today and
    filling each day up to daily_minutes. Use when the student says they fell behind."""
    daily_minutes = daily_minutes or _prefs()["daily_minutes"]
    today = date.today()
    tasks = _load()
    overdue = sorted((t for t in tasks if not t["done"] and t["due_date"] < today.isoformat()),
                     key=lambda t: t["due_date"])
    day, used, moved = today, 0, []
    for t in overdue:
        if used and used + t["est_minutes"] > daily_minutes:
            day, used = day + timedelta(days=1), 0
        old, t["due_date"] = t["due_date"], day.isoformat()
        used += t["est_minutes"]
        moved.append({"title": t["title"], "from": old, "to": t["due_date"]})
    _save(tasks)
    return {"moved": moved, "count": len(moved)}


@mcp.tool()
async def import_syllabus(text: str) -> dict:
    """Read pasted syllabus, course outline or list-of-deadlines text, extract every dated task using
    Amazon Bedrock, and add them all at once. Use this whenever the student pastes a syllabus or
    several assignments and deadlines in one message. Only pass text the student actually pasted;
    never invent or guess syllabus content, and ask them to paste it if they have not."""
    if len(text.strip()) < 40 or not re.search(r"\d", text):
        return {"error": "No real syllabus text was provided. Ask the student to paste it."}
    if not MODEL_ID:
        return {"error": "BEDROCK_MODEL_ID is not set on the server."}
    try:
        found = await asyncio.to_thread(extract_tasks_sync, text[:12000])
    except Exception as e:
        return {"error": f"Could not reach the AI service ({type(e).__name__})."}
    tasks = _load()
    have = {(t["title"].lower(), t["due_date"]) for t in tasks}
    added = []
    for f in found:
        key = (f["title"].lower(), f["due_date"])
        if key in have:
            continue
        have.add(key)
        task = {"id": uuid.uuid4().hex[:6], **f, "done": False}
        tasks.append(task)
        added.append(task)
    _save(tasks)
    return {"added": len(added), "skipped_duplicates": len(found) - len(added), "tasks": added}


@mcp.tool()
def set_preferences(daily_minutes: int | None = None, preferred_time: str | None = None) -> dict:
    """Remember the student's study habits. daily_minutes is how many minutes they can study per day;
    preferred_time is 'morning', 'afternoon' or 'evening'. Call with no arguments to read the current
    settings. Saved settings become the defaults when planning and rescheduling."""
    prefs = _prefs()
    if daily_minutes is not None:
        if not 15 <= daily_minutes <= 720:
            return {"error": "daily_minutes must be between 15 and 720."}
        prefs["daily_minutes"] = daily_minutes
    if preferred_time:
        pt = preferred_time.strip().lower()
        if pt not in ("morning", "afternoon", "evening"):
            return {"error": "preferred_time must be morning, afternoon or evening."}
        prefs["preferred_time"] = pt
    PREFS.write_text(json.dumps(prefs, indent=2))
    return prefs


@mcp.tool()
def weekly_overview(days: int = 7) -> dict:
    """Show the workload for the coming days: study minutes due each day, overdue work, and warnings
    about days that exceed the student's daily goal. Use for questions like 'how does my week look?'."""
    days = max(1, min(days, 14))
    goal = _prefs()["daily_minutes"]
    today = date.today()
    pending = [t for t in _load() if not t["done"]]
    overdue = [t for t in pending if t["due_date"] < today.isoformat()]
    out, warnings = [], []
    for i in range(days):
        d = today + timedelta(days=i)
        due = [t for t in pending if t["due_date"] == d.isoformat()]
        mins = sum(t["est_minutes"] for t in due)
        status = "free" if not due else "overloaded" if mins > goal else "ok"
        if status == "overloaded":
            warnings.append(f"{d:%a %d %b} has {mins} min due, over the {goal} min/day goal.")
        out.append({"date": d.isoformat(), "label": f"{d:%a %d %b}", "minutes": mins,
                    "tasks": [t["title"] for t in due], "status": status})
    if overdue:
        warnings.insert(0, f"{len(overdue)} task(s) are overdue; offer to reschedule them.")
    return {"daily_minutes": goal,
            "overdue": {"count": len(overdue), "minutes": sum(t["est_minutes"] for t in overdue)},
            "days": out, "warnings": warnings}