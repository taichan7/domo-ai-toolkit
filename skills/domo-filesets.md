# Domo FileSets (Documents) API Skill

Use this when a task stores, retrieves, or searches **unstructured files** (documents, images,
transcripts) in Domo — RAG/AI-agent grounding, document pipelines, PDF/image processing — rather than
tabular DataSet rows. It covers the two API surfaces, the full endpoint set, upload mechanics, the
`search`-vs-`query` distinction, and the auth models. Companions: Code Engine mechanics in
[`domo-code-engine.md`](domo-code-engine.md); Pro Code bundle wiring in
[`domo-procode-app.md`](domo-procode-app.md); MCP toolkits in [`domo-mcp-toolkits.md`](domo-mcp-toolkits.md).

> **The whole FileSets / Documents REST API is officially BETA** — Domo's own docs banner it
> "subject to change without notice." Treat every path and shape below as potentially unstable, and
> re-verify against the live instance before relying on anything tagged `[REPO]` or `[INFER]`.

> **Naming.** Domo has rebranded the product to **"Domo Documents (formerly FileSets)."** The REST
> API and KB still say *FileSet*; inside a custom app the API calls the id a **`documentCollectionId`**
> (same thing as `filesetId`). The UI lives under **Data › FileSets** (may now read **Documents**).

## Evidence tiers

Every path/shape line below carries a tier. Anything `[REPO]` or `[INFER]` must be re-verified live
before you depend on it.

```
[DOC]   Official Domo API docs — the machine-readable OpenAPI spec
        (domo.com/docs/openapi/product/filesets.yaml) or the App Framework
        "Documents API" reference. Authoritative, but the API is BETA.
[KB]    Domo Knowledge Base / product pages (e.g. KB article 000005849,
        the "Domo Documents" product page). Product facts, limits, UI behavior.
[REPO]  Verified only against this repo's working usage on a live Domo instance —
        NOT in public docs. May be an internal/undocumented endpoint on a BETA
        API. Re-verify before relying on it.
[INFER] Reasoned from the proxy/manifest model or from Domo-adjacent (community)
        sources — plausible, not first-party documented.
```

(Verified 2026-09-05 by a 17-agent research + adversarial-verify workflow against Domo public docs:
**6 claims CONFIRMED, 2 DOC-ADDS, 1 DOC-SILENT, 2 REFUTED**. The two REFUTED items are called out
explicitly below so they never get written as fact.)

## What a FileSet is

A FileSet is Domo's managed container for **unstructured files** — documents, images, transcripts,
and other common image/document types — rather than tabular DataSet rows. `[KB]` `[DOC]`

- **Path-addressable.** Files live in directories inside the set and are addressable by path (the API
  exposes get/delete "by path" endpoints and `directoryPath` filters). `[DOC]`
- **RAG / AI-agent source.** Enabling **AI Search** indexes a set's contents so it can ground Domo AI
  and AI-agent (Workflow) responses; the content `query` endpoint is the retrieval path. `[KB]`
- **Managed in the UI** under **Data › FileSets** (may read **Documents**), populated by direct upload
  or connectors (Amazon S3, SFTP, GitHub, Google Drive, Confluence). `[KB]`
- **Published limits are thin.** Only file **size** is documented (KB 000005849): images ~3.75 MB,
  documents ~50 MB, manual-UI upload capped at 5 MB. File **count** is stated **"unlimited"** (subject
  to Storage / Retrieval / AI-Search-Indexing consumption charges). Domo does **not** publish API rate
  limits or multipart body-size caps — do not assume they exist. `[KB]`

## Two API surfaces (same endpoints, different prefix + auth)

The same FileSet REST resource is reachable two ways. Pick by **where your code runs**.

| | Server-to-server surface | In-app (App Framework) surface |
|---|---|---|
| **Base path** | `/api/files/v1/filesets/...` `[DOC]` | `/domo/files/v1/filesets/...` `[REPO]` |
| **Caller** | Code Engine (`codeengine.send_request`), Jupyter, provision scripts, any dev-token client | Pro Code app running in the browser (ryuu.js `domo.get/post/put/delete`) |
| **Auth** | CE-injected instance auth (tokenless, preferred) **or** explicit dev token — see Auth section | Session cookie auto-injected by the App Framework proxy; the app author sets no auth header |
| **Official name** | "FileSets API (BETA) (Product)" `[DOC]` | App Framework "Documents API" `[DOC]` |
| **Paths/shapes** | Identical resource model on both — same route suffixes, same request/response bodies `[REPO]` |

- From **Code Engine**, prefer `codeengine.send_request("GET", "/api/files/v1/filesets/...")` — CE injects
  instance auth at runtime, so no token is authored. (See the Auth section for the token-only exceptions.)
- From a **Pro Code browser app**, use the `/domo/files/v1/...` prefix through `domo.*`; the proxy attaches
  the user's session. Do **not** try to send a dev token from browser JS.
- One caveat witnessed in the repo: a **file-content download** in the browser is done with a plain
  `fetch(url)` against the returned content URL, **not** `domo.get(...)` — matching Domo's own doc note that
  the download response is a raw stream, not a JSON body the SDK wrapper expects. `[REPO]`

## Endpoint reference

Route suffixes are identical on both surfaces; prefix with `/api/files/v1` (server) or `/domo/files/v1`
(in-app). `{id}` is the `filesetId` / `documentCollectionId`.

**FileSet lifecycle** (DOC-ADDS — the repo had no lifecycle CRUD; these are documented in the OpenAPI spec):

| Operation | Method + route | Notes | Tier |
|---|---|---|---|
| Create a FileSet | `POST /filesets` | Body carries name/description/AI-search flags; response returns the new id | `[DOC]` |
| List / find FileSets | `POST /filesets/search` | **Metadata** search over sets themselves (paginated); not file content | `[DOC]` |
| Get a FileSet | `GET /filesets/{id}` | Set metadata | `[DOC]` |
| Update a FileSet | `PUT /filesets/{id}` | Mutate set metadata | `[DOC]` |
| Delete a FileSet | `DELETE /filesets/{id}` | Removes the set and its files | `[DOC]` |

**Files inside a set:**

| Operation | Method + route | Notes | Tier |
|---|---|---|---|
| List / search files (metadata) | `POST /filesets/{id}/files/search` | Paginated; body carries filters + `pageContext`/pagination token; returns file metadata | `[REPO]` `[DOC]` |
| Content search (semantic) | `POST /filesets/{id}/files/query` | `query` required; `topK`, `directoryPath` optional; returns chunks with a relevance `score` | `[REPO]` `[DOC]` |
| Upload a file | `POST /filesets/{id}/files` (multipart) | Two parts: `file` + `createFileRequest` JSON — see Upload section | `[REPO]` `[DOC]` |
| Get file metadata | `GET /filesets/{id}/files/{fileId}` | Single file's metadata | `[REPO]` |
| Get file by path | `GET /filesets/{id}/files/path/{directoryPath}` (or `?path=`) | Path-addressed fetch | `[REPO]` |
| Download file content | content URL via plain `fetch` (browser) / `GET .../download` (server) | Raw stream, **not** a JSON body — do not wrap in `domo.get` | `[REPO]` `[DOC]` |
| Delete a file | `DELETE /filesets/{id}/files/{fileId}` (and by-path variant) | Removes one file | `[REPO]` |

- The exact route spellings for file get/delete/download vary between the OpenAPI spec and the in-app proxy;
  the repo pins the working spellings but they are on a **BETA** API — re-verify per instance. `[REPO]`
- `POST /filesets/search` (find sets) and `POST /filesets/{id}/files/search` (find files in one set) are
  **different endpoints at different scopes** — don't conflate them.

## Upload — multipart with a JSON options part

Upload is a **`multipart/form-data`** POST with exactly two parts: `[REPO]` `[DOC]`

1. **`file`** — the raw file bytes (the binary/text content).
2. **`createFileRequest`** — a **JSON** part carrying the file's placement + metadata. The load-bearing
   field is **`directoryPath`** (where in the set the file lands); it also carries the name and any
   content-type/description fields.

Repo shape (server surface, explicit-token path — the one place a dev token is currently required, because
the CE client does not do multipart in this repo; see Auth):

```python
# Two named parts; requests builds the multipart boundary. directoryPath places the file.
files = {
    "file": (filename, file_bytes, mime_type),
    "createFileRequest": (None, json.dumps({"directoryPath": directory_path, "name": filename}),
                          "application/json"),
}
requests.post(f"{host}/api/files/v1/filesets/{fileset_id}/files",
              headers={"X-DOMO-Developer-Token": token}, files=files)
```

Hedges:
- **Part names matter.** `file` and `createFileRequest` are the witnessed names; a plain single-part body
  is rejected. `[REPO]`
- **Do not claim a multipart body-size cap.** Domo publishes per-file *size* limits (≈3.75 MB image /
  ≈50 MB document / 5 MB manual-UI) but **no documented multipart request-size limit** — don't invent one. `[KB]`
- From the **browser** surface, the App Framework proxy handles the multipart POST with session auth; you
  still send the same two parts. `[INFER]`

## `search` vs `query` — two different endpoints

These are the two most-confused endpoints. They serve different jobs. `[REPO]` `[DOC]`

| | `search` | `query` |
|---|---|---|
| **Route** | `POST /filesets/{id}/files/search` | `POST /filesets/{id}/files/query` |
| **Purpose** | Enumerate/filter files by **metadata** (name, path, dates, size) | **Content** retrieval — semantic search over the indexed file contents |
| **Key inputs** | filter object + pagination (`pageContext` / page token) | **`query` (required)** + optional `topK`, `directoryPath` |
| **Returns** | Paginated list of file metadata | Matching content chunks, each with a relevance **`score`** |
| **Needs AI Search?** | No | Yes — the set must be AI-Search-indexed for content retrieval |
| **Use for** | "list what's in this set", housekeeping, pagination | RAG grounding, "find the passage about X" |

- If you want "the files under directory D," that is **`search`** with a path filter (or a directory-scoped
  list) — not `query`. `query` is for *content*, and its `directoryPath` merely **scopes** a content search. `[REPO]`
- `query` results are ranked by `score`; `search` results are not relevance-ranked. `[REPO]`
- `search` is paginated — carry the returned page token forward; don't assume one call returns every file. `[REPO]`

## Directories are implicit

There is **no "create directory" step** in the normal flow. A directory exists because a file was uploaded
with that `directoryPath`. `[REPO]` `[DOC]`

- **Create a path by using it.** Upload with `createFileRequest.directoryPath = "a/b/c"` and the nested path
  is materialized implicitly. You don't pre-create `a`, then `a/b`. `[REPO]`
- **Address by path.** Get/delete-by-path and the `directoryPath` filter/scope on `search`/`query` all
  operate on these implicit paths. `[REPO]`
- **A `/directories` endpoint was *probed* in the repo but its request/response shape is not confirmed and
  it is not in the docs surface we verified.** Treat any explicit directory-create/list call as `[REPO]`/
  `[INFER]` and re-verify live before relying on it — the implicit `directoryPath`-on-upload model is the
  documented, safe path. `[REPO]`

## Auth in depth

Three auth models, one per caller. The general Code-Engine auth rules live in
[`domo-code-engine.md`](domo-code-engine.md); this is the FileSet-specific slice.

**1. Code Engine — tokenless (preferred).** `codeengine.send_request(METHOD, "/api/files/v1/filesets/...")`
uses CE-runtime-injected instance auth. No `X-DOMO-Developer-Token` header is authored. This is the default
for GET/POST/PUT/DELETE metadata, `search`, `query`, and JSON-bodied calls. `[REPO]`

**2. Code Engine — explicit dev token (the exceptions).** In this repo two things fall back to a
`requests` call with `X-DOMO-Developer-Token` + an absolute `domo_hostname`: `[REPO]`
- **Multipart upload** — the CE client isn't used for the two-part `multipart/form-data` POST here, so upload
  goes token-only (`fileset_ops.py` docstring literally says "アップロード（Requests 必須 / マルチパート）").
- **File-content download** — a token path is used as the fast path, with a tokenless fallback.

  Token source in CE = account-property keys tried in order (`password`/`Password`/`Api Key`/`api_key`/
  `token`/`Token`); host = `get_execution_information().domo_hostname` with config/env fallback. Probe both
  `send_request`/`sendRequest` and `get_execution_information`/`getExecutionInformation` casings — the client
  is exposed as `codeengine` and may be absent (`ce = globals().get("codeengine")`). `[REPO]`

  > Whether the multipart/download token-requirement is a *hard* CE limitation or just how this repo wrote it
  > is **not proven** — it's `[REPO]` behavior, not a documented `[DOC]` constraint. If you can make the CE
  > client do multipart, prefer tokenless. The general "prefer CE tokenless; fall back to a token only when
  > the CE client can't do the job" rule is documented in [`domo-code-engine.md`](domo-code-engine.md).

**3. Browser (Pro Code app) — session cookie.** Use `/domo/files/v1/...` via ryuu.js `domo.*`; the App
Framework proxy injects the user's session. The app author sets no auth header, and must **never** embed a
dev token in browser JS. Content download here uses a plain `fetch` on the returned URL. `[REPO]`

## Do NOT claim as documented fact (hedge list)

These came back **REFUTED** or **unverifiable** in the doc cross-check. Do not state them as fact:

1. **A tool named "FileSetReadTool"** (or any specific fixed tool-class name) — REFUTED; no such documented
   name. Describe the *capability*, not an invented identifier.
2. **A documented API rate limit** on FileSet calls — none published. Don't cite a number.
3. **A documented maximum file count per set** — Domo states file count is "unlimited" (consumption-metered),
   not capped. Don't claim a cap.
4. **A documented multipart request-size limit** — not published (per-file *size* limits are; those are different).
5. **Exact route spellings as stable** — the whole API is BETA and "subject to change"; re-verify per instance.
6. **That the `/directories` endpoint create/list shape is known** — it isn't confirmed; treat as `[REPO]`/`[INFER]`.
7. **That multipart upload/content-download *must* use a dev token at the platform level** — that's `[REPO]`
   repo behavior, not a proven CE limitation.
8. **That in-app and server responses differ in shape** — they're the same resource model; don't imply a divergence.
9. **Any consumption/pricing figure as current** — Storage/Retrieval/AI-Search-Indexing are metered, but exact
   rates change; point to Domo billing docs rather than quoting a price.

## Safety / hygiene

- **Deletes are destructive and unconfirmed-by-default here.** `DELETE /filesets/{id}` removes the set and
  all its files; `DELETE .../files/{fileId}` removes one file. On the shared validation instance
  (`maintenance-instance`) only touch FileSets **you created** and clearly named (`zz-*`/`test-*`) — never delete or
  inventory a set you did not create. Verify ownership before any delete.
- **Never author a dev token in browser JS**, and never commit tokens/SIDs. The token-only CE paths read the
  token from account properties at runtime — keep it there, never inline it into a committed file.
- **File contents can be sensitive.** FileSets often hold customer documents. When you read/download for
  debugging, summarize — do not paste raw file bytes or extracted PII into handoffs, commits, or chat.
- **BETA surface = defensive coding.** Wrap calls so an endpoint-shape change degrades gracefully; log the
  route you actually hit so a break is diagnosable.

## Repo precedent

Working FileSet usage already lives in the repo — read these before writing new code (line numbers drift, so
grep the token, not the line): `[REPO]`

| Project | What it demonstrates |
|---|---|
| `news-summary-app/code-engine/fileset_ops.py` | The fullest CE reference: tokenless `send_request` metadata calls, the token-only multipart **upload** (`createFileRequest`) and content **download** with tokenless fallback, `/directories` probe |
| `fileset-manager/fs_bulk_transfer.py`, `fs_delete_skipped.py` | Server-to-server bulk copy/delete via `files/search` metadata pagination |
| `fileset-pdf-to-jpeg-manager/fileset_pdf_to_long_jpeg.py` | PDF→image pipeline: read files from a set, write derived images back |
| `u2s-doc-summary-app/` (`code-engine/`, `jupyter-workspace/`, `pro-code/`) | End-to-end doc pipeline: extract/classify/normalize + browser `query`/path-download UI |
| `security-qa-rag-chat-app/pro-code/app.js`, `rag-chat-app/pro-code/app.js` | Browser RAG surface: `query` for retrieval, get-meta, and **content download via plain `fetch` (not `domo.get`)** |
| `domo-support/new/support-center/pro-code/domo-access.js` | In-app `/domo/files/v1/...` proxy access pattern |

Companion skills: [`domo-code-engine.md`](domo-code-engine.md) (auth + CE mechanics),
[`domo-procode-app.md`](domo-procode-app.md) (browser bundle wiring),
[`domo-mcp-toolkits.md`](domo-mcp-toolkits.md) (agent-driven Domo access).
