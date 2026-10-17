# Quickstart - 15 minutes from zero to your first AI-powered Domo workflow

> Japanese: [quickstart.ja.md](quickstart.ja.md)

This guide walks you through the first three things you can do with this repo. By the end, you will have:

1. Authenticated to your Domo instance from the terminal
2. Listed and queried a dataset
3. Asked an AI agent to do the same thing for you, in plain English

---

## What you need

- A Domo account that can log in to your instance
- A terminal (Terminal on macOS, PowerShell or Git Bash on Windows, any shell on Linux)
- Node.js installed (for the Domo CLI)
- Python 3 installed (the helper scripts use it)
- `curl` installed (the helper scripts use it; preinstalled on macOS and most Linux, and available in Git Bash on Windows)
- Either the **Domo CLI** logged in, OR a **developer token** from your Admin panel

---

## Step 1 — Install the Domo CLI (one time)

```bash
npm install -g ryuu
```

Then log in:

```bash
domo login
```

A browser window opens. Pick your instance, sign in, and approve the CLI. The CLI saves a refresh token locally so you do not have to do this again for this instance.

Verify:

```bash
domo whoami
```

You should see your instance and your user.

---

## Step 2 — Authenticate this repo's scripts

```bash
cd domo-ai-toolkit
bash scripts/authenticate.sh your-company.domo.com
```

(Replace `your-company.domo.com` with your actual instance domain.)

If it reports authentication succeeded for the requested instance, you are ready. The script saves an owner-only, git-ignored `../scripts/.sid` file for the other scripts. Credentials are not printed. Do not copy or share the SID or authentication headers.

---

## Step 3 — List datasets

```bash
bash scripts/list-datasets.sh
```

You should see the first 50 datasets in your instance, with their ID, name, type, row count, and owner. To get more, pass a number:

```bash
bash scripts/list-datasets.sh 200   # fetch the first 200 in pages of 50
```

---

## Step 4 — Run SQL against a dataset

Pick any dataset ID from the list above. Then:

```bash
bash scripts/query-dataset.sh <dataset-id> "SELECT * FROM table LIMIT 5"
```

The table name is always `table` — it refers to the dataset itself. You can use any standard SQL:

```bash
bash scripts/query-dataset.sh <id> "SELECT COUNT(*) FROM table"
bash scripts/query-dataset.sh <id> "SELECT * FROM table WHERE status = 'open' LIMIT 10"
bash scripts/query-dataset.sh <id> "SELECT \`Column Name\` FROM table LIMIT 5"
```

Use `LIMIT 0` to see only the column list (schema discovery):

```bash
bash scripts/query-dataset.sh <id> "SELECT * FROM table LIMIT 0"
```

---

## Step 5 — Diagnose failing ETLs

```bash
bash scripts/diagnose-etls.sh
```

This lists every Magic ETL dataflow whose last run failed, grouped by error code. To drill into one specific failure:

```bash
bash scripts/diagnose-etls.sh <flow-id>
```

You will see the failing tile, the expression or join keys involved, and which error code came back. Match the code against the table in `api-reference.md` for a recommended fix.

---

## Step 6 — Hand it all to an AI agent

Open the repo in Claude Code, Codex, Cursor, or your preferred AI coding agent. The agent should read `AGENTS.md` first; Claude Code starts from `CLAUDE.md`, which points there.

Try asking:

> "List the 10 datasets with the most rows in my instance."

> "Find every failing Magic ETL and group them by error code."

> "Look at dataflow 92 — what's broken and how would you fix it?"

The agent will use the same scripts and patterns you just learned manually. The difference: it can chain them together, summarize the results, and write follow-up queries based on what it finds.

See `ai-agent-setup.md` for the full agent setup.

---

## Common issues

**`domo: command not found`**
The CLI installed but is not on your PATH. On macOS/Linux, restart your terminal. On Windows, restart PowerShell.

**`ERROR: no ryuu config for X found`**
You have not run `domo login` against that instance yet. Run it and pick the right instance.

**Authentication works but list-datasets prints nothing**
Your account may not have read access on any datasets in this instance. Check with your Domo admin.

**`401 Unauthorized` mid-run**
The SID expired (it lasts roughly an hour). Re-run `bash scripts/authenticate.sh <instance>` and try again.

**SQL returns no columns**
Make sure the SQL is valid — try it in Domo's Analyzer first. Check that column names with spaces use backticks (`` `Column Name` ``), not quotes.

---

## What's next

- Read `api-reference.md` for the full endpoint list and patterns
- Open `../templates/pro-code-app/` to see a working Pro Code app skeleton you can build on
- Read `ai-agent-setup.md` to configure an AI agent against this repo
