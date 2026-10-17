# StudyPilot

**An Alexa+ study planner that turns your deadlines into a daily plan.**

StudyPilot is a self-hosted [MCP](https://modelcontextprotocol.io) server (Streamable HTTP, spec
2025-11-25) that lets an AI assistant such as Alexa+ capture study tasks, read a syllabus, and plan
your day. Built for the Amazon *Build, Ship, Shape* hackathon (Alexa+ track, AWS Builder mini-challenge).

A web-based Alexa+ simulator is included so you can try the full experience without a device.

## What it can do

Say things like:

- "I have a physics lab due Friday, about 45 minutes."
- "What should I study tonight? I have 2 hours."
- "I fell behind, please fix my schedule."
- "I can study 90 minutes a day, mostly in the evening."
- Paste a syllabus and StudyPilot adds every deadline for you.

## MCP tools

| Tool | What it does |
|---|---|
| `add_task` | Add a study task with subject, due date and estimated minutes |
| `list_tasks` | List open tasks, soonest first |
| `update_task` | Change a task's title, due date or estimate |
| `complete_task` | Mark a task done |
| `delete_task` | Delete a task |
| `plan_day` | Fill the available time with the most urgent tasks |
| `reschedule_overdue` | Catch-up plan: spread overdue tasks across the coming days |
| `weekly_overview` | Workload per day for the next week, with overload warnings |
| `set_preferences` | Remember daily study minutes and preferred time of day |
| `import_syllabus` | Extract every dated task from pasted syllabus text (uses Amazon Bedrock) |

Tasks and preferences persist between sessions (`tasks.json`, `prefs.json`).

## How it works

```
Browser simulator ──> /chat ──> Amazon Bedrock (Converse API, tool use)
        │                              │ decides which tools to call
        └────────────> /mcp/ <─────────┘
                         │   MCP server (Python, FastAPI)
                         └─ tools ──> tasks.json / prefs.json
                                  └─> Bedrock (import_syllabus)
```

- **MCP server:** `server_mcp.py` (tools) mounted at `/mcp/` by `server.py`, using the official MCP
  Python SDK with stateless Streamable HTTP.
- **Amazon Bedrock:** `chat.py` gives the model the MCP tool list through the Converse API and runs the
  tools it chooses. `llm.py` uses Bedrock to turn pasted syllabus text into structured tasks.
- **Simulator:** `static/index.html` is a single-page mock Alexa+ with a live task panel.

## Quick start

Requires Python 3.10+ and an AWS account with Amazon Bedrock model access.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export AWS_REGION=us-east-1                          # region where you enabled the model
export BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0      # a model or inference profile ID you can use
# AWS credentials: run `aws configure`, or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

python -m uvicorn server:app --reload
```

Then open <http://localhost:8000/>. In GitHub Codespaces, open port 8000 from the **Ports** tab.

Tested with Amazon Nova Pro (`us.amazon.nova-pro-v1:0`). Any Bedrock text model that supports tool use
in the Converse API should work. Never commit AWS keys; use environment variables or Codespaces secrets.

## Try it

1. Click **Load demo tasks** (four tasks, two overdue).
2. Click **Week ahead** to see the workload chart, then **I fell behind** to reschedule.
3. Type a request such as "Add a chemistry quiz due Monday, 40 minutes."
4. Click **Import syllabus**, paste a list of deadlines, and watch the tasks appear.

## Testing the MCP server directly

```bash
curl -L -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Project layout

```
server.py       FastAPI app: mounts /mcp/, /chat and the simulator page
server_mcp.py   MCP server and all tools
chat.py         Natural-language endpoint (Bedrock Converse + tool use)
llm.py          Bedrock helper for syllabus extraction
static/         Simulator UI
```

## Known limitations

- Single-user demo storage in local JSON files; no authentication.
- The simulator stands in for Alexa+; connecting a live Alexa+ device was not tested.

## What's next

Spaced-repetition reminders, exam countdowns, calendar sync, and voice input.

## License

MIT. See [LICENSE](LICENSE).