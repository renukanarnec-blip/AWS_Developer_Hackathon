"""Shared Amazon Bedrock helpers: syllabus text -> structured study tasks."""
import json
import os
import re
from datetime import date, datetime

import boto3

# .strip() guards against the hidden-newline problem with pasted secrets
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "").strip()
client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1").strip())

EXTRACT_PROMPT = """Extract every study task, assignment, quiz, exam or deadline from the syllabus text below.
Today is {today}. Return ONLY a JSON array and nothing else. Each item must look like:
{{"title": "...", "subject": "...", "due_date": "YYYY-MM-DD", "est_minutes": 60}}
Rules:
- Resolve relative or partial dates using today's date (use the next upcoming occurrence).
- Skip anything that has no date.
- est_minutes is a realistic estimate: quiz 30-60, assignment 60-120, essay 120-180, exam prep 120-240.
- subject is the course name if stated, otherwise "General".
- At most 30 items.

SYLLABUS:
{text}"""


def parse_tasks(raw: str) -> list[dict]:
    """Pull a JSON array out of the model's reply and keep only valid items."""
    raw = re.sub(r"<thinking>.*?</thinking>", "", raw, flags=re.S)
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for it in items:
        try:
            datetime.strptime(it["due_date"], "%Y-%m-%d")
            out.append({"title": str(it["title"])[:120],
                        "subject": str(it.get("subject") or "General")[:60],
                        "due_date": it["due_date"],
                        "est_minutes": max(15, min(480, int(it.get("est_minutes") or 60)))})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def extract_tasks_sync(text: str) -> list[dict]:
    prompt = EXTRACT_PROMPT.format(today=f"{date.today():%A, %Y-%m-%d}", text=text)
    resp = client.converse(modelId=MODEL_ID, messages=[{"role": "user", "content": [{"text": prompt}]}],
                           inferenceConfig={"maxTokens": 2000, "temperature": 0})
    raw = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    return parse_tasks(raw)