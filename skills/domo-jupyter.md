# Domo Jupyter (Workspaces) Skill

Use this skill when working with **Domo Jupyter Workspaces** (the premium in-platform JupyterLab environment), notebook-derived scripts, `domojupyter` code, Jupyter DataFlows, or Workflow "Domo Jupyter" tasks. It answers the recurring question **"can Jupyter be deployed / automated via API?"** and maps everything a workspace can do.

## Evidence tiers

```text
[DOC]   first-party API reference: developer.domo.com, the OpenAPI YAML under domo.com/docs/openapi, or a first-party SDK ref.
        (A domo.com/docs/s/article/<12-digit> page is a Salesforce KB = [KB], NOT [DOC].)
[KB]    Domo Knowledge Base / documented product behavior.
[SDK]   official first-party `domojupyter` package source (public conda channel), read directly (v1.1.43, 2026-09-13).
        Authoritative for what the library calls; NOT a public contract for those internal endpoints.
[REPO]  verified only against this repo's working code.
[INFER] reasoned, or inferred-from-absence. A fetch FAILURE (404 / JS-gate / login-wall) is MISSING evidence, never proof of absence.
```

On disagreement, take the **more conservative** tier. The single guarded failure mode is **over-claiming** — presenting an undocumented route, an inference-from-absence, or an untested runtime behavior as if it were a documented public contract. For this surface the key untested area is the **internal `/api/datascience/v1/...` API family** (engineered for use *inside* a running workspace): its endpoint map is `[SDK]`, its external-caller behavior is `[INFER]`.

## Headline answers (the API/deploy question)

1. **Deploy a workspace/notebook via REST? No documented public API exists** for creating/starting/stopping/deleting a workspace, uploading/downloading `.ipynb` files, attaching DataSets/accounts/File Shares, or scheduling a notebook. The published OpenAPI catalog in `llms.txt` contains **no Jupyter spec** (`[DOC]`, checked 2026-09-13), the KB describes every one of those as a UI action (`[KB]`), and `domo publish`/the Domo CLI cover **Custom Apps only** (`[REPO]` — `domo --help` has no Jupyter command). Practical code deployment = **UI upload** or **Git push/pull from inside a running workspace** (`[KB]`).
2. **What *is* API-reachable:**
   - **Notebook execution** — start a Workflow that contains a native **Domo Jupyter** action via the documented Workflows API (`POST /api/workflow/v1/instances/message`; the spec itself names Jupyter-Workspace scripts as consumers) → `domo-workflow.md` (`[DOC]`).
   - **Model registration (the real "deploy models from Jupyter")** — from *inside* a notebook, `domojupyter.ai.model.create_model(...)` creates the AI Model Management record and uploads the model package; later deployment as endpoint / Magic ETL tile is UI-driven (`[KB]`/`[SDK]`).
   - **DataSet write-back, AppDB, accounts, AI** — from inside the notebook via `domojupyter` (`[SDK]`); from outside, use the ordinary DataSet / AppDB / AI Services APIs.
   - **Jupyter DataFlow run** — the repo's `POST /api/dataprocessing/v1/dataflows/{id}/executions` pattern is `[REPO]` for Magic ETL flows; applying it to a `JUPYTER`-engine DataFlow is `[INFER]` (not executed here).
3. **Internal API family** `https://{instance}.domo.com/api/datascience/v1/workspaces/{workspaceId}/...` exists and is what the SDK calls (`[SDK]`), but it is **undocumented, workspace/session-bound, and not intended for external automation**. Do not build on it; use it only as explanatory evidence for what the SDK does.

## Naming traps — read this first

| You see… | It actually is… | Owner |
|---|---|---|
| **Jupyter Workspace** | the container: JupyterLab env + kernel + compute tier + input/output DataSets + accounts + File Shares | **this skill** |
| **Jupyter notebook** | one `.ipynb` file inside a workspace; multiple per workspace | **this skill** |
| **Jupyter DataFlow** | a *scheduled notebook* — a DataFlow with engine `JUPYTER`, created by **Schedule Notebook**; only ONE scheduled DataFlow per workspace | **this skill** (scheduling) → `domo-magic-etl.md` (engine/tile facts) |
| **`domojupyter`** | the in-workspace Python SDK (`import domojupyter as domo`) | **this skill** |
| **`domo-jupyter` / `domo-jupyter-notebook`** | Domo's library/kernel distribution names (conda channel) — not an API | **this skill** |
| **AI prompts in Jupyter / Jupyter AI** | `domojupyter.ai.*` calls routed through the workspace (`/api/datascience/.../ai/...`); the **platform** AI Services API (`/api/ai/v1/...`) is a different transport/auth/response shape | `domo-ai-services.md` |
| **AI Model Management** | the model registry/deployment area that Jupyter models land in; **registration** happens in-notebook | **this skill** (registration) / `domo-magic-etl.md` (AI Model Inference tile) |
| **Workflows "Domo Jupyter" action** | a native workflow task (AI Tools) that runs a notebook with a payload | `domo-workflow.md` |
| **Notebook card** | a classic Domo card type (Doc/Notebook card) — unrelated to Jupyter Workspaces | `domo-cards.md` |
| **File Share** | a Jupyter-attached persistent directory (grants: Create/Manage Fileshare Directories) — **not** FileSets, **not** the Files API | **this skill** / `domo-filesets.md` / `domo-files.md` |
| **"deploy"** | ambiguous: (a) upload notebook code → manual/Git; (b) deploy a *model* → in-notebook SDK + UI; (c) execute notebook → Workflows / DataFlow | **this skill** |

## Capability map — what a Jupyter Workspace can do

### 1. Author and run notebooks

- **JupyterLab interface**; kernels are **Python or R**; cells are code/markdown/raw; Run All; File Browser; integrated terminal (`File > New > Terminal`) (`[KB]`).
- **Persistent home directory** (`/path/to/home` appears in Domo's GitHub article); notebooks and files survive stops; **multiple notebooks per workspace** (`[KB]`).
- **Libraries**: install with `conda install <pkg> -y` (or pip/cran fallbacks) from the terminal; Domo's base env does not guarantee every third-party lib; no JupyterLab plugins; no code copilot (`[KB]`).
- **Kernel snapshots** capture the customized conda env (used to make model hosting match the dev env); restore-to-base-env (Manage Kernel Snapshots) and "Restore Kernel Defaults" are UI actions — the latter requires all instances stopped (`[KB]`).
- **Workspace stop/start**: workspace runs while you use it; **Timeout** (inactivity) auto-stops it (default **8 hours**) (`[KB]`).

### 2. Workspace configuration and lifecycle

- **Grants**: `Create Jupyter Workspace` (create/edit/delete owned workspaces) or `Manage Jupyter Workspace` (Jupyter Admin — view/edit/delete any; required to enable sharing). File Share adds `Create/Manage Fileshare Directories` (`[KB]`).
- **Enable**: Admin must activate the **Jupyter** feature (`Admin > Features > Jupyter`); account plan Default (all users, unlimited) vs Manual (per-user usage policies); compute tier limit (`[KB]`).
- **Create modal options**: Name (characters `[:*?"<>|]` unsupported), Description, **Kernel**, **Compute Tier Limit**, **Timeout**, **Start workspace on successful creation**, optional **Input DataSets**, **Output DataSets**, **Accounts**, **File Shares** (`[KB]`).
- **Run**: select workspace → Start; takes several seconds (`[KB]`).
- **Edit**: change specs (kernel requires the workspace stopped) (`[KB]`).
- **Delete**: irreversible (`[KB]`).
- **Share**: an Admin/Manage-grant user must **Enable Sharing** first, then the owner shares with permissions; co-owners can add instances; **simultaneous editing is not supported**; co-owners can see referenced third-party accounts (but not key values) and share I/O DataSets (`[KB]`).
- **Tiers**: trial customers see 4 tiers; consumption customers up to 9 tiers (different CPU allocations); tier limits configured by Admin (`[KB]`).

### 3. DataSet I/O (the core integration)

From the notebook via `domojupyter` (`import domojupyter as domo`):

- **Prerequisite**: the DataSet must be configured on the workspace — **input** DataSets for reads, **output** DataSets for writes; the SDK resolves by **alias or id** (`[KB]`/`[SDK]`).
- **Read** — `domo.read_dataframe(dataset, query=None, nlq=None, **kwargs)`:
  - `dataset` = input alias or UUID; optional `query` = SQL string executed server-side; optional `nlq` = natural-language question converted via `text_to_sql` then executed (if both `query` and `nlq` are given, `nlq` is ignored) (`[KB]`/`[SDK]`).
  - Returns a pandas DataFrame; Domo column types are mapped to pandas dtypes and date-like columns are parsed unless the caller overrides `dtype`/`parse_dates` (`[SDK]`).
  - Internally it calls `GET/POST /api/query/v1/execute/export/{datasourceId}` with `Accept: text/csv` and parses CSV (`[SDK]`). (The externally documented face of that endpoint is owned by `domo-query-dataset.md`; do not conflate the SDK's CSV consumption with the documented JSON envelope.)
- **Write** — `domo.write_dataframe(df, dataset, update_method=None, update_key=None, partition_name=None)`:
  - **Default is REPLACE**. Modes: `"REPLACE"`, `"APPEND"`, `"UPSERT"` (needs `update_key`), `"PARTITION"` (needs `partition_name`); invalid values raise (`[KB]`/`[SDK]`).
  - **Schema rule (silent-failure trap)**: if the DataFrame schema != the current output schema, `UPSERT`/`APPEND`/`PARTITION` **raise** (schema must match exactly); `REPLACE` simply replaces the schema. `UPSERT` also rewrites the schema's identity object to `update_key` (`[SDK]`).
  - Rows are uploaded in **50,000-row CSV parts** (gzip-compressed), then the execution is committed (with `partitionName` for PARTITION) (`[SDK]`).
  - Duplicate column names in the DataFrame schema raise; **UPSERT fails on duplicate values in the key column** (`[KB]`/`[SDK]`).
  - The UI doc's rule of thumb: a new DataSet is created for each **output** added to the workspace (`[KB]`).

### 4. Accounts (stored credentials)

- `domo.get_account_property_value(account, key)` returns one property value; `domo.get_account_property_keys(account)` lists properties; `account` = account id or alias configured on the workspace (`[KB]`/`[SDK]`).
- Values are pulled from the platform account store at runtime — **never hard-code credentials in notebooks** (`[KB]` hygiene).
- The underlying route is `/api/datascience/v1/workspaces/{id}/account/{accountId}` (`[SDK]`); external Account CRUD is owned by `domo-accounts-connectors.md`.

### 5. AppDB (JSON document store)

- `domo.app_db` exposes `get_document`, `get_documents`, `query_documents`, `create_document`, `create_documents`, `delete_document`, `delete_documents`, `update_document`, `update_documents` (`[SDK]`).
- Collection is addressed by **collectionId or alias** from the workspace's `collectionConfiguration` (AppDB collections must be attached to the workspace for aliases to resolve) (`[SDK]`).
- Create/update helpers auto-wrap bare dicts in the AppDB `{ "content": ... }` envelope if absent; `query_documents` stringifies its `jsonQuery` (`[SDK]`).
- External AppDB API semantics (sync, permissions, query grammar) → `domo-appdb.md`.

### 6. Domo AI from inside the notebook

- Exported helpers (`[KB]`/`[SDK]`): `text_to_sql`, `generate_text`, `text_to_beast_mode`, `summarize`, `image_to_text`, `chat_completion`, `messages`, `tool_calling`, `embedding`, `image_embedding`, `classification`, `sentiment`. (The `Domo` client in `domo.py` also carries `planning` and `targeted_sentiment` methods; neither has a wrapper exported from `domojupyter.ai` in v1.1.43.)
- Common optional args: `prompt_template`, `parameters`, `model`, `model_configuration`, `system`; text generation adds `temperature`, `maxTokens`, `response_format`, `reasoning_config`; summarization adds `chunking_configuration` (`ChunkingConfiguration`), `output_style` (`SummarizationOutputStyle.BULLETED|NUMBERED|PARAGRAPH`), `output_word_length` (`SizeBoundary`) (`[KB]`).
- Return shape is `TextAIResponse {prompt, choices}` (`[SDK]`); the KB's text-to-SQL example reads `.choices[0]['output']`.
- **Transport separation**: these calls go through the workspace route `/api/datascience/v1/workspaces/{id}/ai/...` (`[SDK]`), NOT the platform AI Services API (`/api/ai/v1/...`). Same product family, different host/auth/response conventions — the `.output` vs `choices[0].output` trap belongs to `domo-ai-services.md`; do not transplant expectations between them.

### 7. Environment snapshots

- `domojupyter.snapshot.create_snapshot(name, block=True)` creates a snapshot of the current Python environment; with `block=True` it polls every 5s until status `SUCCESS` (raises with `failureReason` on `FAILED`) and returns the snapshot object; `list_snapshots()` lists all snapshots (`[SDK]`).
- The UI manages the same objects (**Manage Kernel Snapshots**, restore-to-base) (`[KB]`).
- A snapshot is created automatically the first time a model is created; later models reuse the most recent snapshot unless `create_snapshot=True` (creating one can take minutes) (`[KB]`/`[SDK]`).
- Snapshot IDs are the environment contract used by model hosting — keep them compatible with the code being registered (`[KB]`).

### 8. Model training → AI Model Management registration

- `domojupyter.ai.model.create_model(name, entrypoint, files, snapshot_id=None, create_snapshot=False, description=None, training=None, tasks=None)` returns the **model id** (`[KB]`/`[SDK]`).
- **Ordering (verified from SDK source)**: resolve/choose snapshot → `POST .../models` (expects **201**, returns model record) → tar.gz the entrypoint + `files` → `POST .../models/{modelId}/package` (expects **204**). A failure on the model-record POST means the package was **never uploaded** (`[SDK]`/`[REPO]` handoff).
- **Tasks**: `ModelTaskType` enum includes `BINARY_CLASSIFICATION`, `CLASSIFICATION`, `REGRESSION`, `SUMMARIZATION`, `TEXT_GENERATION`, `CHAT_COMPLETION`, `TASK_PLANNING`, `TEXT_EMBEDDING`, `IMAGE_GENERATION`, `FORECASTING`, `OTHER`; I/O schemas via `CSVModelIOConfiguration` (can infer columns/dtypes from a DataFrame) or `JSONModelIOConfiguration`; metrics via `Metric`, hyperparameters/algorithm via `ModelTrainingInformation` (`[SDK]`).
- **Deployment targets after registration** (UI): real-time model **endpoint** (start/stop on the AI Models page; test input/output; endpoint logs) and **Magic ETL** via `Action menu > Deploy to ETL` — **any model with CSV input + an output task** can become an AI Model Inference tile (`[KB]`).
- The model code exposes an `invoke(data, content_type_header, accept_header)` entrypoint when used as a DataFlow tile (CSV string in/out) (`[KB]`).
- **Hard-won compatibility lesson (`[REPO]` 2026-07-25)**: the optional `training` object can trigger an opaque **HTTP 500** on the model-record POST (extra hyperparameters/metrics changed vs a previously accepted payload). Recovery: **omit `training`** (keep full metrics in local files), publish only previously accepted bounded metadata, reuse the latest snapshot (`create_snapshot=False`), and do **not** auto-retry (ambiguous retries can create duplicate model records). Decouple training from registration (`DEPLOY_ONLY`-style path). A 500 does not mean the model files are bad.

### 9. Scheduling and execution

- **Schedule Notebook** (toolbar) creates a **Jupyter DataFlow** with engine `JUPYTER`: choose compute tier + schedule (daily/several times a day/weekly/monthly/specific days, etc.). It appears in Data Center → DataFlows; **only ONE scheduled DataFlow per Jupyter workspace** (a second notebook cannot be scheduled); Settings/DataSets/Lineage tabs are empty — History and Versions are the meaningful ones; **Edit in Jupyter** opens the source notebook (`[KB]`).
- **Manual run**: DataFlow options → **Run** (UI). **Download output** per execution: IPYNB / HTML / PDF (`[KB]`).
- **Execution logs for debugging**: the workspace keeps a `recent_executions` directory with `output.ipynb`, `output.html`, `output.pdf`, `stdout`, `stderr` (`[KB]`).
- **Workflows execution**: add the native **Domo Jupyter** action (AI Tools category) to a workflow; it needs the **Workspace ID**, the **notebook path**, and the execution **payload**. In the notebook, `domojupyter.execution.get_payload()` reads the payload and `write_response(...)` is **required** to return output to the workflow (`[KB]`/`[SDK]`). See the dual-mode rules in §11.
- **Triggering that workflow by API** (documented, outside-the-workspace path): `POST /api/workflow/v1/instances/message` (`{messageName, version, modelId, data}`); the product spec explicitly names "scripts running in Domo's Jupyter Workspaces" as a consumer. Details, auth, and status enums → `domo-workflow.md` (`[DOC]`).
- **Direct DataFlow execution API**: this repo's Magic ETL deployers use `POST /api/dataprocessing/v1/dataflows/{id}/executions` (+ `GET .../executions`) (`[REPO]`). A Jupyter DataFlow is a DataFlow, but **running a JUPYTER-engine one over that API was not verified here** — treat as `[INFER]` and probe read-only first.

### 10. GitHub integration

- A workspace can act as a Git client: open a terminal, `git config`, `ssh-keygen -t ed25519`, add the public key to GitHub, `git init`/remote, then **push updates (including notebook files) to GitHub** and pull changes (`[KB]` 000005166).
- This is the closest thing to a code-deployment pipeline for Jupyter: keep the `.ipynb`/`.py` in the repo, `git pull` inside the workspace (or edit in Jupyter and push out). It is still human/workspace-driven — there is no CI hook on Domo's side.
- In this repo the established deployment practice is **manual upload / git sync, treated as a human-gated deploy** (`[REPO]`: multiple handoffs state "Jupyter deploy is manual upload, no autonomous deploy path").

### 11. Dual-mode scripts (Workflow + Jupyter) — required coding rules

- Prefer repeatable scripts (`main.py`, `processor.py`, project modules) over notebook-only logic; keep notebooks as exploration/reporting artifacts.
- **Separate "no payload" from "payload errored" when detecting mode.** Do not wrap the payload fetch in a broad `except Exception` that routes `None` to the manual/Jupyter path: a transient payload-fetch error during a real Workflow run would silently misroute to the manual path (e.g., appending a synthetic placeholder row and dropping the real triggering record). Catch only the specific context-absent signal and re-raise everything else, or pass an explicit mode flag.
- Document input/output Dataset names or aliases; the Workflows mode returns `{status: "Success"|"Failed"}` via `domo_exec.write_response(...)` and re-raises on error so the workflow sees the failure.
- Respect API limits, add retry/checkpoint behavior for long jobs, and avoid loading unbounded data when sampling/pagination is enough.
- Never commit raw customer exports, secrets, SID files, tokens, cookies, or credentials; keep generated outputs out of git unless they are intentionally small fixtures.

### 12. Consumption, limits, and operational notes

- Consumption = **tier × runtime (rounded up to 5-minute intervals) + 1 credit per DataSet write**; scheduled Jupyter DataFlows consume the same way (workspace starts → notebook runs → stops) (`[KB]`).
- **Stop workspaces when done**; set a reasonable Timeout; minimize DataSet writes; start at a lower tier (`[KB]`).
- **Jupyter cannot run continuously as a hosted service/API** — it is not a server runtime (`[KB]` FAQ).
- Usage can be monitored at Admin → Usage → **Jupyter Compute** (grants: View Usage Metrics + Manage Jupyter Workspaces) (`[KB]`).
- Troubleshooting quick map: workspace won't start → usage policy/tier config; kernel restarting → OOM (raise tier); library install failure → conda/pip compatibility, restore base kernel; scheduled execution failure → run cells in order, inspect `recent_executions/` (`[KB]`).

## Automation / API matrix

| Task | Documented public API? | Actually available path | Tier |
|---|---|---|---|
| Create / edit / share / delete workspace | **No** | UI only | `[KB]` |
| Start / stop workspace | **No** | UI (timeout auto-stop); implied by schedule/Workflow runs | `[KB]` |
| Upload / download notebook files | **No** | UI upload/download; `git` in the workspace terminal | `[KB]` |
| Attach Input/Output DataSets, Accounts, File Shares | **No** | UI (Edit Workspace) | `[KB]` |
| Schedule a notebook | **No** | UI **Schedule Notebook** → Jupyter DataFlow | `[KB]` |
| Run a notebook | Indirect | Start a Workflow containing the **Domo Jupyter** action via `POST /api/workflow/v1/instances/message` | `[DOC]` |
| Run a Jupyter DataFlow directly | **No (unverified)** | Repo pattern `POST /api/dataprocessing/v1/dataflows/{id}/executions` (proven for MAGIC; JUPYTER `[INFER]`) | `[REPO]`/`[INFER]` |
| Register a trained model | In-notebook SDK | `domojupyter.ai.model.create_model(...)` → AI Model Management | `[KB]`/`[SDK]` |
| Deploy a model to endpoint / Magic ETL | **No** | AI Models UI | `[KB]` |
| Read/write DataSets from a notebook | In-notebook SDK | `read_dataframe` / `write_dataframe` | `[KB]`/`[SDK]` |
| AppDB read/write from a notebook | In-notebook SDK | `domojupyter.app_db.*` | `[SDK]` |
| AI calls from a notebook | In-notebook SDK | `domojupyter.ai.*` (workspace route) | `[KB]`/`[SDK]` |
| Deploy via `domo` CLI | **No** | CLI is Custom Apps only (`publish/download/...`) | `[REPO]` |

**Published-catalog check (`[DOC]`, 2026-09-13):** `domo.com/docs/llms.txt` lists every Platform/Product/Framework OpenAPI spec; none is Jupyter/DataScience. `llms-full.txt` (18.4 MB) contains **no** `/api/datascience` reference. So "no documented workspace-management API" is a catalog-level absence — still phrase as "not documented" (`[INFER]`-grade as a universal negative), never as proof that no internal route exists.

**Internal API family — read through the SDK, do NOT build on it** (`[SDK]`, official `domojupyter` 1.1.43 source). Base: `https://{DOMO_HOSTNAME}/api/datascience/v1/workspaces/{DOMO_WORKSPACE_ID}` (JupyterHub-flavored variants under `{JUPYTERHUB_SERVICES_URL}/domo/v1/workspaces/{id}?workspace_session_id=...`). Auth is workspace-session-bound (`DomoHubAuthentication` mints a bearer via the workspace `auth/token`; also `X-DOMO-Developer-Token` / `X-DOMO-Resource-Token` variants). Endpoints the SDK calls:

| Area | Route (relative to the workspace base) |
|---|---|
| Workspace descriptor (input/output/collection config) | `GET /workspaces/{id}` |
| DataSet schema | `GET`/`PUT /data/{dataSourceId}/schema` |
| DataSet upload execution | `POST /data/{dataSourceId}/executions?updateMethod=...`; `PUT .../executions/{executionId}/part/{partId}` (gzip CSV); `PUT .../executions/{executionId}/commit[?partitionName=]` |
| Workspace auth token | `GET /workspaces/{id}/auth/token` (via `{JUPYTERHUB_SERVICES_URL}/domo/v1/...`) |
| Accounts | `GET /account/{accountId}` |
| AppDB collections | `GET/POST /collection/{collectionId}/document`; `GET .../documents`; `POST .../query`; `POST .../delete/document/{id}`; `POST .../delete/documents`; `PUT .../document`; `PUT .../update/documents` |
| Snapshots | `POST`/`GET /snapshots` |
| Workflow payload/response | `GET .../notebooks/{notebookId}/dataflow/executions/{executionId}/payload`; `POST .../notebooks/{notebookId}/dataflow/executions/{executionId}` |
| Models | `POST /models` (201); `POST /models/{modelId}/package` (204) |
| AI | `POST /ai/text/sql`, `/ai/text/generation`, `/ai/text/beastmode`, `/ai/text/summarize`, `/ai/image/text`, `/ai/text/chat`, `/ai/messages/chat`, `/ai/messages/tools`, `/ai/text/plan`, `/ai/embedding/text`, `/ai/embedding/image`, `/ai/classification`, `/ai/sentiment`, `/ai/targeted-sentiment` |
| DataSet export (read) | `GET`/`POST /api/query/v1/execute/export/{datasourceId}` with `Accept: text/csv` (absolute path — not under the workspace base) |

## `domojupyter` SDK reference (v1.1.43)

- **Public API** (`from domojupyter import ...`): `read_dataframe`, `write_dataframe`, `get_account_property_value`, `get_account_property_keys`, `enable_dprint`, `dprint`; plus first-class modules `domojupyter.ai`, `domojupyter.app_db`, `domojupyter.snapshot`, `domojupyter.execution`, `domojupyter.io`, `domojupyter.domo`.
- **Latest published version on the public conda channel**: 1.1.43 (channel `https://domo-conda-prod.s3.amazonaws.com/domo`; versions seen 1.1.15 → 1.1.43). The KB's `conda install ... domojupyter=1.1.32` example lags; `check_version` prints the upgrade command when the channel advertises newer (`[SDK]`).
- **Environment variables injected by the runtime** (`[SDK]`): `DOMO_HOSTNAME`, `DOMO_WORKSPACE_ID`, `DOMO_WORKSPACE_SESSION_ID`, `DOMO_NOTEBOOK_ID`, `DOMO_NOTEBOOK_EXECUTION_ID`, `DOMO_RESOURCE_TOKEN` (dataflow runs), `JUPYTERHUB_SERVICES_URL`, `JUPYTERHUB_API_TOKEN`, `DOMO_CONDA_CHANNEL`. Scripts should read auth from these — never embed tokens.
- **Auth modes** (`[SDK]`): `DomoHubAuthentication` (JupyterHub token → workspace bearer, auto-refresh with 30s buffer), `DomoDevTokenAuthentication` (`X-DOMO-Developer-Token`), `DomoResourceTokenAuthentication` (`X-DOMO-Resource-Token`, dataflow execution context), `DomoDataflowAuthentication` (bearer obtained via the resource token — used by `execution.py`/`app_db.py`/`ai/` when `DOMO_RESOURCE_TOKEN` is present).
- **`execution` module** (`[SDK]`): `get_payload()` → workflow payload JSON; `write_response(jsonable)` → posts the response (expects HTTP 204). Both use the injected `DOMO_NOTEBOOK_ID`/`DOMO_NOTEBOOK_EXECUTION_ID`; outside a workflow execution context the requests fail — this is the dual-mode signal (catch narrowly, see §11).
- **`io` module details** (`[SDK]`): input/output resolution by `dataSourceId` first, then `alias`; write validates duplicate column names and schema compatibility; type conversion helpers map pandas ↔ Domo types (`datetime64` → date parsing on read; ints/floats/strings/objects on write).
- **`snapshot` module** (`[SDK]`): `create_snapshot(snapshot_name, block=True)`, `list_snapshots()`.
- **`app_db` module** (`[SDK]`): see §5; collection alias resolution reads `workspace['collectionConfiguration']`.
- **`ai` module** (`[SDK]`): see §6; request/response models under `domojupyter.ai.models` (`PromptTemplate`, `DataSourceSchema`, `ChunkingConfiguration`, `SeparatorType`, `SummarizationOutputStyle`, `SizeBoundary`, `Metric`, `ModelTask`, `ModelTaskType`, `CSVModelIOConfiguration`, `JSONModelIOConfiguration`, `ModelTrainingInformation`, `Tool`, `Image`, `ClassificationLabel`, `SentimentTopic`, ...).

## Repo precedent (what exists in this workspace)

| Path | What it demonstrates |
|---|---|
| `jupyter-workspace/kana_normalize.py` + `tests/test_kana_normalize.py` | Dual-mode (Workflow payload vs manual Jupyter constants) utility; hermetic tests stub `domojupyter`(+`.execution`) via `sys.modules`/`spec_from_file_location`; source not modified to test |
| `u2s-doc-summary-app/jupyter-workspace/u2s_extract_classify_normalize.py` + tests | Workflow payload contract (`get_payload`/`write_response`, `{status: Failed}` on bad payload); **manual upload deploy is GATED** — "自律デプロイ経路がない（手動アップロード）" (handoff 2026-09-07); test-only characterization of pure logic |
| `internal-apps/marketdata/jupyter-workspace/{feature-label,return-forecast/work}` | Production ML pipeline (train → `./models` → daily inference → DataSet writes); `domojupyter.ai.model.create_model` registration retried manually; manual upload per README ("After manually updating the Domo Jupyter Workspace files, run the stages") |
| `internal-apps/j-quants_v2/*` | Same ML/registration pattern; `register_model()` wraps `ml.create_model` with snapshot reuse |
| `fileset-pdf-to-jpeg-manager/fileset_pdf_to_long_jpeg.py` | Jupyter + Workflow dual-runtime script (workflow payload → Jupyter mode fallback) |
| `production-priority-app/jupyter-workspace/` (retired) | A Jupyter optimizer later superseded by Magic ETL DF3063 — historical example only |

**Deployment practice in this repo**: Jupyter sources are deployed by **manual upload/git sync inside the workspace**, treated as human-gated; there is no `domo publish` equivalent for Jupyter. Keep repo sources canonical and note when workspace and repo may drift.

## Testing and validation

- Compile with `python3 -m py_compile <script>.py`.
- For notebook-derived scripts, include a dry-run/sample mode when practical.
- **Hermetic test pattern**: stub `domojupyter` / `domojupyter.execution` (and submodules actually referenced) with `types.ModuleType` + `sys.modules.setdefault(...)`, load the target module via `importlib.util.spec_from_file_location`, and test only **owned pure logic**. The official SDK's own tests require a live workspace and cannot run offline; never make repo tests call Domo.
- Never point tests at a live workspace or real instance; record any Domo environment checks that were not performed.
- For model registration, make the register step independently invocable (`DEPLOY_ONLY`-style) and keep metrics/hyperparameters locally so a registry failure does not force retraining.

## DO-NOT guards (numbered)

1. **Do NOT claim a documented public REST API exists** for workspace CRUD, start/stop, notebook upload/download, DataSet/account attachment, or notebook scheduling. The published OpenAPI catalog has no Jupyter spec; those are UI/Git actions (`[KB]`/`[DOC]`). The claim "no internal route exists" stays `[INFER]` — only "not documented" is provable.
2. **Do NOT call `/api/datascience/v1/workspaces/...` from outside a running workspace** as if it were supported: auth is JupyterHub/session-bound and external behavior is `[INFER]`. Do not build automations on the SDK's internal routes.
3. **Do NOT log, commit, or hard-code tokens/SIDs/refresh tokens** in notebooks or scripts — read the injected `DOMO_*`/`JUPYTERHUB_*` env vars via the SDK auth classes.
4. **Do NOT write with a mismatched schema under `UPSERT`/`APPEND`/`PARTITION`** — the SDK raises; use `REPLACE` to change schema deliberately.
5. **Do NOT `UPSERT` without `update_key`**, and never with duplicate key values (fails per docs).
6. **Do NOT `PARTITION` without `partition_name`** (raises).
7. **Do NOT expect arbitrary DataSets to be readable/writable from a notebook** — they must be configured on the workspace as Input (read) or Output (write), addressed by alias or id.
8. **Do NOT detect Workflow-vs-Jupyter mode with a broad `except Exception`** around `get_payload()` — a transient error in a real Workflow run would silently take the manual path. Catch only the context-absent signal or pass an explicit flag.
9. **Do NOT assume multiple scheduled notebooks per workspace** — only one Jupyter DataFlow per workspace is allowed.
10. **Do NOT build on `recent_executions/` contents as an API** — it is a debugging artifact.
11. **Do NOT interpret a model-registration HTTP 500 as a training/model defect**; it is a registry-metadata failure. Omit `training`, reuse the latest snapshot, keep rich metrics local, and do not blindly retry (duplicate model records).
12. **Do NOT transplant expectations between Jupyter AI and the platform AI Services API** — different route, auth, and response shape (`TextAIResponse {prompt, choices}` here).
13. **Do NOT leave workspaces running** (billing continues) and do not treat Jupyter as a continuous service — it cannot host a long-running API.
14. **Do NOT conflate File Share with FileSets / the Files API**, or Jupyter workspaces with classic **Notebook cards**.
15. **Do NOT expect plugins or a code copilot** — unsupported in Jupyter Workspaces.
16. **Do NOT assume Git sync is automated** — Domo does not run CI on workspace repos; pulls/pushes are manual [KB].
17. **Do NOT try to deploy Jupyter content with `domo publish`** — the CLI handles Custom Apps only (`[REPO]`).
18. **Do NOT run a JUPYTER DataFlow through the dataflow executions API as if proven** — the repo pattern is proven for MAGIC flows; JUPYTER is `[INFER]`, probe read-only first.
19. **Do NOT report this skill as asserting runtime behavior that was never executed** — this skill executed **zero** live workspace operations; every endpoint/runtime claim is `[KB]`/`[SDK]`/`[REPO]`-as-noted, and external-caller behavior is `[INFER]`.

## Companion skills / defers

- `domo-magic-etl.md` — **JUPYTER engine** DataFlow facts (type `"JUPYTER"`, dataset `displayType`/`dataProviderType = domo-jupyterdata`, History-only tabs, one scheduled dataflow per workspace) and the **AI Model Inference tile**.
- `domo-workflow.md` — the **Domo Jupyter action** (config: Workspace ID + notebook path + payload), the Workflows start API, triggers, and instance status.
- `domo-ai-services.md` — the **platform** AI Services API (`/api/ai/v1/...`), model list/response conventions, and the `.output` vs `choices[0].output` trap.
- `domo-datasets.md` — DataSet REST (query/upload/stream/permissions) used when a notebook writes back or external code manages DataSets.
- `domo-appdb.md` — AppDB REST worlds/sync/permissions; this skill only owns the in-notebook SDK face.
- `domo-filesets.md` / `domo-files.md` — unstructured-file storage; **not** Jupyter File Share.
- `domo-cards.md` — classic card types including Notebook cards.
- `domo-code-engine.md` — the server-side sibling runtime; choose CE for tokenless internal APIs/light logic, Jupyter for exploration/ML/heavy Python.
- `domo-sandbox.md` — content promotion/version control between instances; Jupyter workspace content is not part of its standard content set (treat as `[INFER]`).

## Sources / verification provenance

- **KB**: `36004740075` (Jupyter Workspaces User Guide), `7440921035671` (Troubleshooting), `000005544` (Use AI Prompts in Jupyter), `Understand-Jupyter-Workspace-Consumption`, `000005291` (Create a Model in Jupyter Workspaces), `000005502` (Manage AI Models and Projects), `000005166` (Use Jupyter Workspaces with GitHub), `000005331` (Workflows AI Tools — Domo Jupyter action, via repo reference).
- **Portal/OpenAPI**: `domo.com/docs/portal/data-science/jupyter`, `/docs/portal/API-Reference/overview` (Product API scope), `openapi/product/workflows-api.yaml` (names Jupyter-Workspace scripts as API consumers).
- **SDK**: official `domojupyter` **1.1.43** package fetched from the public Domo conda channel (`domo-conda-prod.s3.amazonaws.com/domo/noarch/domojupyter-1.1.43-py_142.tar.bz2`, plus `repodata.json` version history 1.1.15→1.1.43); modules `io.py`, `domo.py`, `app_db.py`, `execution.py`, `snapshot.py`, `jupyterhub.py`, `ai/ai.py`, `ai/model.py`, models, `__init__.py`, `update.py` read directly on 2026-09-13.
- **Catalog check**: `domo.com/docs/llms.txt` + `llms-full.txt` (18,423,763 bytes) grepped 2026-09-13 — no Jupyter/DataScience OpenAPI spec; zero `/api/datascience` occurrences.
- **Execution**: documentation-only. No workspace was created/started, no notebook was uploaded or run, no internal endpoint was called, and no credentials were read. The `[SDK]` endpoint map is source-derived, not live-verified.
