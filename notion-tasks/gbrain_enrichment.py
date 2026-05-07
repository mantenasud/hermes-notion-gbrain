"""
gbrain_enrichment.py

Runs weekly via cron. Fetches all Notion tasks updated in the last 7 days,
groups them by project, distils each group into a summary using OpenAI
(reusing GBrain's existing API key), and writes the result to GBrain as
a knowledge page — one page per project.

Cron example (every Sunday at 8pm):
  0 20 * * 0 /path/to/venv/bin/python3 /path/to/gbrain_enrichment.py >> /home/ubuntu/logs/gbrain_enrichment.log 2>&1
"""

import sys
import os
import requests
import subprocess
import tempfile
from datetime import date, timedelta
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "your_notion_token_here")
DATABASE_ID  = os.environ.get("NOTION_DATABASE_ID", "your_database_id_here")
GBRAIN       = os.environ.get("GBRAIN_PATH", "/home/ubuntu/.bun/bin/gbrain")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Map Notion project page IDs → human-readable project names
# Replace these with your own project page IDs
PROJECT_IDS = {
    "your_techtalk_page_id":       "Techtalk",
    "your_hermes_page_id":         "Hermes",
    "your_ai_automation_page_id":  "AI Automation",
    "your_accounting_page_id":     "Accounting",
    "your_farm_house_page_id":     "Farm House",
    "your_family_page_id":         "Family",
}

# ── OpenAI client — reuses GBrain's existing key ──────────────────────────────
def get_openai_client():
    result = subprocess.run(
        [GBRAIN, "config", "get", "openai_api_key"],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        print("❌ Could not retrieve OpenAI key from GBrain config")
        sys.exit(1)
    return OpenAI(api_key=result.stdout.strip())

# ── Notion: fetch tasks updated in the last 7 days ───────────────────────────
def fetch_recent_tasks():
    since = (date.today() - timedelta(days=7)).isoformat()
    payload = {
        "filter": {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": since}
        }
    }
    r = requests.post(
        f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
        headers=NOTION_HEADERS, json=payload
    )
    r.raise_for_status()
    return r.json().get("results", [])

def extract_task_info(page):
    props  = page["properties"]
    name   = props.get("Task name", {}).get("title", [{}])
    name   = name[0].get("text", {}).get("content", "Untitled") if name else "Untitled"
    status = props.get("Status", {}).get("status", {})
    status = status.get("name", "—") if status else "—"
    due    = props.get("Due", {}).get("date") or {}
    due    = due.get("start", "—")
    project_relations = props.get("Project", {}).get("relation", [])
    project_ids = [r["id"].replace("-", "") for r in project_relations]
    return {
        "name":        name,
        "status":      status,
        "due":         due,
        "project_ids": project_ids
    }

# ── Group tasks by project ────────────────────────────────────────────────────
def group_by_project(tasks):
    grouped = {name: [] for name in PROJECT_IDS.values()}
    grouped["Unassigned"] = []
    for task in tasks:
        matched = False
        for pid in task["project_ids"]:
            project_name = PROJECT_IDS.get(pid)
            if project_name:
                grouped[project_name].append(task)
                matched = True
        if not matched:
            grouped["Unassigned"].append(task)
    return {k: v for k, v in grouped.items() if v}

# ── OpenAI: distil tasks into a knowledge page summary ───────────────────────
def distil(client, project_name, tasks):
    task_lines = "\n".join(
        f"- {t['name']} | {t['status']} | due {t['due']}"
        for t in tasks
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": "You update knowledge base pages. Be concise and factual."
            },
            {
                "role": "user",
                "content": f"""Project: {project_name}
Tasks from this week:
{task_lines}

Write 4-8 bullet points covering:
- What is actively being worked on
- What was completed this week
- Patterns or priorities you notice
- People or dependencies mentioned in task names

Plain bullets starting with •. Present tense for active items, past tense for completed."""
            }
        ]
    )
    return response.choices[0].message.content.strip()

# ── GBrain: write or update a page using slug + put command ──────────────────
def update_gbrain(project_name, summary):
    week_label = date.today().strftime("Week of %d %b %Y")
    slug       = f"{project_name.lower().replace(' ', '-')}-active-context"
    title      = f"{project_name} — Active Context"
    content    = f"# {title}\n_{week_label}_\n\n{summary}"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        tmpfile = f.name

    try:
        with open(tmpfile, 'r') as f:
            result = subprocess.run(
                [GBRAIN, "put", slug],
                stdin=f,
                capture_output=True, text=True
            )
        if result.returncode == 0:
            print(f"✅ GBrain updated: {slug}")
        else:
            print(f"❌ GBrain failed for {project_name}: {result.stderr.strip()}")
    finally:
        os.unlink(tmpfile)

# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print(f"🔄 GBrain enrichment — {date.today()}")

    client = get_openai_client()
    pages  = fetch_recent_tasks()

    if not pages:
        print("No tasks updated this week — nothing to enrich.")
        return

    tasks  = [extract_task_info(p) for p in pages]
    groups = group_by_project(tasks)

    for project_name, project_tasks in groups.items():
        if project_name == "Unassigned":
            print(f"⚠️  Skipping {len(project_tasks)} unassigned tasks")
            continue
        print(f"📋 Processing {project_name} ({len(project_tasks)} tasks)...")
        summary = distil(client, project_name, project_tasks)
        update_gbrain(project_name, summary)

    print("✅ Enrichment complete.")

if __name__ == "__main__":
    run()
