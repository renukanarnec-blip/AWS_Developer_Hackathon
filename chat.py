"""Natural-language layer: Amazon Bedrock (Converse API) decides which MCP tools to call."""
import asyncio
import os
from datetime import date

import boto3
from fastapi import APIRouter
from pydantic import BaseModel

from server_mcp import mcp  # the MCP server defined in server.py (see wiring below)

router = APIRouter()
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")  # copy a model ID from the Bedrock console
client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))


class ChatIn(BaseModel):
    message: str


async def tool_config() -> dict:
    """Turn the MCP tool list into Bedrock's toolSpec format."""
    tools = await mcp.list_tools()
    return {"tools": [{"toolSpec": {"name": t.name, "description": t.description or "",
                                    "inputSchema": {"json": t.inputSchema}}} for t in tools]}


async def run_tool(name: str, args: dict) -> str:
    """Call the tool through the MCP server and return its result as text."""
    result = await mcp.call_tool(name, args)
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(getattr(c, "text", str(c)) for c in content)


@router.post("/chat")
async def chat(body: ChatIn):
    if not MODEL_ID:
        return {"reply": "Set BEDROCK_MODEL_ID first (see README)."}
    system = [{"text": f"You are StudyPilot, a friendly study assistant. Today is {date.today():%A, %Y-%m-%d}. "
                       "Use the tools to manage the student's tasks. Convert relative dates to YYYY-MM-DD. "
                       "Keep replies short and spoken-friendly."}]
    messages = [{"role": "user", "content": [{"text": body.message}]}]
    cfg = await tool_config()
    for _ in range(5):  # allow a few tool-use rounds
        resp = await asyncio.to_thread(client.converse, modelId=MODEL_ID, system=system,
                                       messages=messages, toolConfig=cfg)
        msg = resp["output"]["message"]
        messages.append(msg)
        if resp["stopReason"] != "tool_use":
            return {"reply": "".join(b.get("text", "") for b in msg["content"])}
        results = []
        for block in msg["content"]:
            if "toolUse" in block:
                tu = block["toolUse"]
                try:
                    out = await run_tool(tu["name"], tu["input"])
                    results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"text": out}]}})
                except Exception as e:
                    results.append({"toolResult": {"toolUseId": tu["toolUseId"], "status": "error",
                                                   "content": [{"text": str(e)}]}})
        messages.append({"role": "user", "content": results})
    return {"reply": "Sorry, that took too many steps. Try a simpler request."}
