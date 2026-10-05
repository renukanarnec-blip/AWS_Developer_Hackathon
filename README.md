# StudyPilot

A self-hosted MCP server (Streamable HTTP, spec 2025-11-25) that lets an AI assistant such as Alexa+
capture study tasks and plan the day. Built for the Amazon "Build, Ship, Shape" hackathon (Alexa+ track).

## Run
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    uvicorn server:app --reload

- Simulator (mock Alexa+): http://localhost:8000/
- MCP endpoint: http://localhost:8000/mcp/

## Tools
`add_task`, `list_tasks`, `complete_task`, `plan_day`
