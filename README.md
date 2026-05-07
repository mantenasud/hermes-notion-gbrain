# Hermes × Notion × GBrain

Natural language task management via WhatsApp and Slack, backed by Notion,
with automatic weekly knowledge enrichment into GBrain.

---

## What This Does

Send a message on WhatsApp or Slack like:

> _"Follow up with the vendor sales rep on Thursday"_

And the agent will:
1. Infer that this is a task creation request
2. Detect the project (Sales-project, in this case)
3. Convert the relative date to `YYYY-MM-DD`
4. Create the task in your Notion database under the correct project
5. Confirm with a ✅

Every Sunday, a cron job pulls all tasks updated that week, distils them into
project-level summaries using OpenAI, and writes the results to GBrain as
knowledge pages — so your AI agent accumulates context about what you are
working on without you doing anything manually.

---

## Architecture

```
WhatsApp / Slack
       ↓
    Hermes agent (AWS VPS)
       ↓  intent inference via system_prompt
  notion_tasks.py  ────────────────────→  Notion database
       
  gbrain_enrichment.py (weekly cron)
       ↓  fetches last 7 days of tasks
    OpenAI gpt-4o-mini (distil)
       ↓
    GBrain (knowledge pages per project)
```

**Components:**
- [Hermes](https://github.com/nousresearch/hermes) — open-source AI agent with WhatsApp and Slack interfaces
- [Notion](https://notion.so) — task database
- [GBrain](https://github.com/garrytan/gbrain) — personal knowledge graph with vector search
- `notion_tasks.py` — thin Python wrapper around the Notion REST API
- `gbrain_enrichment.py` — weekly cron that distils Notion tasks into GBrain knowledge pages

---

## Prerequisites

- Hermes installed and running on a VPS (Ubuntu recommended)
- GBrain installed and initialised (`gbrain init`)
- A Notion account with a task database
- OpenAI API key configured in GBrain (`gbrain config set openai_api_key sk-...`)
- Python 3.11+ with `requests` available

---

## Setup

### 1. Create a Notion Integration

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **New integration**, name it (e.g. "Hermes Agent"), select your workspace
3. Copy the **Internal Integration Token** — this is your `NOTION_TOKEN`
4. Open your tasks database in Notion → click `...` (top right) → **Connections** → add your integration
5. Also add the integration to every **parent page** that contains the database

### 2. Get Your Database ID

Open your Notion database in a browser. The URL looks like:

```
https://www.notion.so/yourworkspace/90a025v1...?v=...
```

The 32-character string before the `?v=` is your `NOTION_DATABASE_ID`.

### 3. Get Your Project Page IDs

For each project page inside your database, open it in the browser and copy
the ID from the URL in the same way. You will need one ID per project.

### 4. Install the scripts

```bash
mkdir -p ~/.hermes/skills/productivity/notion-tasks/scripts
cp notion-tasks/notion_tasks.py ~/.hermes/skills/productivity/notion-tasks/scripts/
cp notion-tasks/gbrain_enrichment.py ~/.hermes/skills/productivity/notion-tasks/scripts/
```

### 5. Configure credentials

Edit both scripts and fill in:

```python
NOTION_TOKEN = "secret_xxxxxxxxxxxxxxxxxxxx"
DATABASE_ID  = "your_database_id_here"
```

In `notion_tasks.py`, update the `PROJECTS` dict with your project page IDs:

```python
PROJECTS = {
    "Sales-project":   "your_sales-project_page_id",
    "hermes":          "your_hermes_page_id",
    # add more as needed
}
```

In `gbrain_enrichment.py`, update `PROJECT_IDS` (reverse map — page ID → name):

```python
PROJECT_IDS = {
    "your_Sales-project_page_id":   "Sales-project",
    "your_hermes_page_id": "Hermes",
    # add more as needed
}
```

Also set the correct path to your GBrain binary:

```python
GBRAIN = "/home/ubuntu/.bun/bin/gbrain"   # find yours with: which gbrain
```

### 6. Verify your Notion column names

Run a quick search to confirm which column names your database uses:

```bash
python3 - <<'EOF'
import requests, json
NOTION_TOKEN = "your_token"
r = requests.post("https://api.notion.com/v1/search",
    headers={"Authorization": f"Bearer {NOTION_TOKEN}",
             "Content-Type": "application/json",
             "Notion-Version": "2022-06-28"},
    json={})
print(json.dumps(r.json(), indent=2)[:3000])
EOF
```

The script defaults to `Task name`, `Status`, `Due`, and `Project`. If your
database uses different names, update the corresponding `props.get(...)` calls
in both scripts.

### 7. Test the scripts directly

```bash
# List all tasks
python3 ~/.hermes/skills/productivity/notion-tasks/scripts/notion_tasks.py list

# Create a task
python3 ~/.hermes/skills/productivity/notion-tasks/scripts/notion_tasks.py \
  create "Test task" "In progress" 2026-05-10 farm

# Mark done
python3 ~/.hermes/skills/productivity/notion-tasks/scripts/notion_tasks.py \
  done "Test task"

# Run enrichment manually
python3 ~/.hermes/skills/productivity/notion-tasks/scripts/gbrain_enrichment.py
```

### 8. Configure Hermes

Add the contents of `notion-tasks/hermes_system_prompt.md` to your Hermes
`~/.hermes/config.yaml` — both the `system_prompt` block and the
`channel_prompts.default` block.

Update the project keyword mapping in the system_prompt to match your projects.

Restart Hermes after editing:

```bash
pkill -f hermes && hermes &
```

### 9. Schedule weekly GBrain enrichment

```bash
crontab -e
```

Add (runs every Sunday at 8pm):

```
0 20 * * 0 /home/ubuntu/.hermes/hermes-agent/venv/bin/python3 \
  /home/ubuntu/.hermes/skills/productivity/notion-tasks/scripts/gbrain_enrichment.py \
  >> /home/ubuntu/logs/gbrain_enrichment.log 2>&1
```

Use the Python binary from Hermes's venv — it has the `openai` package already
installed. Find your venv path with:

```bash
find /home/ubuntu/.hermes -name "python3" -type f
```

---

## Usage

Once set up, send natural language messages from WhatsApp or Slack:

| Message | What happens |
|---|---|
| `Follow up with vendor sales rep on Thursday` | Creates task under inferred project, converts date |
| `Sign the legal contracts before Saturday` | Marks matching task as Done |
| `What's still pending?` | Lists all open tasks |
| `Push the supplier call to next Friday` | Updates due date |
| `Drop the old budget task` | Archives the task |
| `Schedule sales demo for Monday` | Creates task under Sales-project project |

No explicit commands needed — Hermes infers intent from natural language.

---

## How GBrain Enrichment Works

Every Sunday, `gbrain_enrichment.py`:

1. Queries Notion for all tasks edited in the last 7 days
2. Groups them by project
3. Sends each group to OpenAI `gpt-4o-mini` for distillation
4. Writes a summary page to GBrain per project (slug: `Sales-project-active-context`, etc.)

The OpenAI API key is read directly from GBrain's config — no separate key needed.

After the first run, GBrain will contain pages like:

```
# Sales-project — Active Context
Week of 07 May 2026

• Sign the legal contracts — due 09 May
• Follow-up with legal team — key external dependency
• AWS installation completed this week
• 3 of 5 tasks marked Done this week
```

These pages compound over time as GBrain's weekly `put` overwrites with the
latest summary, keeping each project page current.

---

## Troubleshooting

**400 error from Notion API**
Your integration does not have access to the database. Open the database in
Notion → `...` → Connections → add your integration. Also add it to the parent
page if the database is nested.

**Hermes responds without running the script**
The LLM is hallucinating. Ensure both `system_prompt` and
`channel_prompts.default` contain the Notion Tasks block. The key phrase is:
_"Hermes has NO internal task list. The ONLY way to create tasks is by running
notion_tasks.py via execute_code."_

**GBrain `Unknown command: page`**
Your GBrain version uses `put <slug>` not `page create`. Run `gbrain --help`
to confirm available commands.

**ModuleNotFoundError: openai**
Use the Python binary from Hermes's venv, which already has openai installed:
`/home/ubuntu/.hermes/hermes-agent/venv/bin/python3`

**Tasks created without a project**
The project keyword was not matched. Check the `PROJECTS` dict in
`notion_tasks.py` and the project mapping in the Hermes system_prompt.

---

## Project Structure

```
hermes-notion-gbrain/
├── README.md
├── .env.example
├── .gitignore
└── notion-tasks/
    ├── notion_tasks.py          # Notion task CRUD via REST API
    ├── gbrain_enrichment.py     # Weekly cron: Notion → OpenAI → GBrain
    └── hermes_system_prompt.md  # Hermes config blocks to copy-paste
```

---

## Contributing

PRs welcome. Useful additions:

- Support for additional Notion property types (priority, assignee)
- Daily digest skill — summarise today's tasks via WhatsApp
- Multi-database support
- Tests

---

## Related Projects

- [Hermes](https://github.com/nousresearch/hermes) — the agent framework this runs on
- [GBrain](https://github.com/garrytan/gbrain) — the knowledge graph this enriches
- [Notion API docs](https://developers.notion.com)

---

## License

MIT
