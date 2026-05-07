import sys
import os
import requests

# ── Config ───────────────────────────────────────────────────────────────────
# Set these in your environment or replace directly
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "your_notion_token_here")
DATABASE_ID  = os.environ.get("NOTION_DATABASE_ID", "your_database_id_here")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

BASE = "https://api.notion.com/v1"

# ── Project mapping: keyword → Notion project page ID ────────────────────────
# Replace these page IDs with your own Notion project page IDs
PROJECTS = {
    "Techtalks":      "your_techtalks_page_id",
    "hermes":         "your_hermes_page_id",
    "ai automation":  "your_ai_automation_page_id",
    "ai":             "your_ai_automation_page_id",
    "accounting":     "your_accounting_page_id",
    "farm house":     "your_farm_house_page_id",
    "family":         "your_family_page_id",
}

def resolve_project(keyword):
    if not keyword:
        return None
    return PROJECTS.get(keyword.lower().strip())

# ── Notion API helpers ────────────────────────────────────────────────────────
def query_db(filter_obj=None, sorts=None):
    payload = {}
    if filter_obj:
        payload["filter"] = filter_obj
    if sorts:
        payload["sorts"] = sorts
    r = requests.post(
        f"{BASE}/databases/{DATABASE_ID}/query",
        headers=HEADERS, json=payload
    )
    r.raise_for_status()
    return r.json().get("results", [])

def find_task_by_name(name):
    return query_db(filter_obj={
        "property": "Task name",          # adjust if your title column has a different name
        "title": {"contains": name}
    })

def format_task(page):
    props  = page["properties"]
    name   = props.get("Task name", {}).get("title", [{}])
    name   = name[0].get("text", {}).get("content", "Untitled") if name else "Untitled"
    status = props.get("Status", {}).get("status", {})
    status = status.get("name", "—") if status else "—"
    due    = props.get("Due", {}).get("date") or {}
    due    = due.get("start", "—")
    return f"• {name} | Status: {status} | Due: {due}"

def create_page(properties):
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties
    }
    r = requests.post(f"{BASE}/pages", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

def update_page(page_id, properties=None, archived=False):
    payload = {"archived": archived}
    if properties:
        payload["properties"] = properties
    r = requests.patch(f"{BASE}/pages/{page_id}", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()

# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_create(args):
    """
    Usage: create <task name> [status] [due YYYY-MM-DD] [project]
    Example: create "Fix irrigation pump" "In progress" 2026-05-10 farm
    """
    if not args:
        print("❌ Usage: create <task name> [status] [due YYYY-MM-DD] [project]")
        return

    name    = args[0]
    status  = args[1] if len(args) > 1 else "In progress"
    due     = args[2] if len(args) > 2 else None
    project = args[3] if len(args) > 3 else None

    properties = {
        "Task name": {"title": [{"text": {"content": name}}]},
        "Status":    {"status": {"name": status}},
    }
    if due:
        properties["Due"] = {"date": {"start": due}}

    project_id = resolve_project(project)
    if project_id:
        properties["Project"] = {"relation": [{"id": project_id}]}

    page = create_page(properties)
    project_label = project.title() if project else "No project"
    print(f"✅ Created: {name} | {status} | Project: {project_label} (ID: {page['id'][:8]})")


def cmd_list(args):
    """
    Usage: list [status]
    Example: list "In progress"
    """
    filter_obj = None
    if args:
        filter_obj = {
            "property": "Status",
            "status": {"equals": " ".join(args)}
        }
    pages = query_db(
        filter_obj=filter_obj,
        sorts=[{"property": "Due", "direction": "ascending"}]
    )
    if not pages:
        print("No tasks found.")
        return
    for p in pages:
        print(format_task(p))


def cmd_update(args):
    """
    Usage: update <task name> status|due <value>
    Example: update "Fix pump" status Done
             update "Fix pump" due 2026-05-15
    """
    if len(args) < 3:
        print("❌ Usage: update <task name> status|due <value>")
        return

    field = args[-2].lower()
    value = args[-1]
    name  = " ".join(args[:-2])

    pages = find_task_by_name(name)
    if not pages:
        print(f"❌ No task found matching: {name}")
        return
    page_id = pages[0]["id"]

    if field == "status":
        update_page(page_id, {"Status": {"status": {"name": value}}})
        print(f"✅ Updated '{name}' → Status: {value}")
    elif field == "due":
        update_page(page_id, {"Due": {"date": {"start": value}}})
        print(f"✅ Updated '{name}' → Due: {value}")
    else:
        print(f"❌ Unknown field: {field}. Use 'status' or 'due'")


def cmd_done(args):
    """
    Usage: done <task name>
    Example: done "Fix irrigation pump"
    """
    if not args:
        print("❌ Usage: done <task name>")
        return
    name  = " ".join(args)
    pages = find_task_by_name(name)
    if not pages:
        print(f"❌ No task found matching: {name}")
        return
    update_page(pages[0]["id"], {"Status": {"status": {"name": "Done"}}})
    print(f"✅ Marked done: {name}")


def cmd_delete(args):
    """
    Archives (soft-deletes) a task. Notion API does not support hard deletion.
    Usage: delete <task name>
    """
    if not args:
        print("❌ Usage: delete <task name>")
        return
    name  = " ".join(args)
    pages = find_task_by_name(name)
    if not pages:
        print(f"❌ No task found matching: {name}")
        return
    update_page(pages[0]["id"], archived=True)
    print(f"🗑️ Archived: {name}")


# ── Dispatcher ────────────────────────────────────────────────────────────────
COMMANDS = {
    "create": cmd_create,
    "list":   cmd_list,
    "update": cmd_update,
    "done":   cmd_done,
    "delete": cmd_delete,
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: notion_tasks.py <command> [args...]")
        print("Commands: create | list | update | done | delete")
        sys.exit(1)

    command = sys.argv[1].lower()
    rest    = sys.argv[2:]

    if command in COMMANDS:
        COMMANDS[command](rest)
    else:
        print(f"❌ Unknown command: {command}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
