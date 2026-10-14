#!/usr/bin/env python3
"""Deploy updated TextGeneration system prompts to a Domo Magic ETL DataFlow via REST.

Magic ETL v2 dataflows (`magic:true`, `databaseType:MAGIC`) are edited in place —
there is no draft/version/release cycle like Workflows have. This script makes that
edit safe with a full backup + surgical single-field edits + strict round-trip verify:

  1. GET the live dataflow definition (authoritative) and back it up to disk
  2. For each (TILE_NAME, PROMPT_MD): extract the fenced ``` ... ``` instructions
     block from the canonical .md and swap ONLY that TextGeneration tile's
     `instructions` (tile matched by name; type asserted TextGeneration)
  3. PUT the modified definition
  4. GET it back and verify: action count identical, action ids identical, ONLY the
     target tiles changed, each target tile's non-instruction fields untouched, and
     `gui` (the visual graph) byte-identical. A no-op PUT of a Magic ETL v2 def has
     been shown to round-trip cleanly on this instance, so any extra diff here means
     the edit was not surgical — we restore the backup and abort.
  5. If RUN=1, trigger an execution so the output columns (店舗別/全社AIサマリー) regenerate.

On any verify failure the backup is PUT back (restore) and the script exits non-zero.

Env: INSTANCE, SID (set via `domo login` + the session-SID helper in docs/setup-guide.md); RUN=1 to also trigger a re-run.
     BACKUP defaults to /tmp/df_<id>_backup.json.
Args: DATAFLOW_ID  TILE_NAME PROMPT_MD  [TILE_NAME PROMPT_MD ...]

Example (deploy both AI-summary tiles and re-run):
  RUN=1 python3 scripts/deploy_dataflow_prompt.py 2042 \
    店舗別AIサマリー生成 prompts/prompt_dataflow_store_summary.md \
    全社AIサマリー生成   prompts/prompt_dataflow_company_summary.md
"""
import json, os, sys, re, urllib.request, urllib.error

INSTANCE = os.environ["INSTANCE"]
SID = os.environ["SID"]
DATAFLOW_ID = sys.argv[1]
PAIRS = sys.argv[2:]  # TILE_NAME PROMPT_MD ...
assert PAIRS and len(PAIRS) % 2 == 0, "args: DATAFLOW_ID TILE_NAME PROMPT_MD [TILE_NAME PROMPT_MD ...]"
TILES = list(zip(PAIRS[0::2], PAIRS[1::2]))
DO_RUN = os.environ.get("RUN") == "1"
BACKUP = os.environ.get("BACKUP", f"/tmp/df_{DATAFLOW_ID}_backup.json")

BASE = f"https://{INSTANCE}/api/dataprocessing/v1/dataflows/{DATAFLOW_ID}"
HDR = {"X-Domo-Authentication": SID, "Content-Type": "application/json"}


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=HDR)
    with urllib.request.urlopen(r, timeout=120) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def extract_instructions(md_path):
    """Canonical dataflow-prompt .md -> the fenced ``` ... ``` instructions block."""
    text = open(md_path, encoding="utf-8").read()
    m = re.search(r"```\n(.*?)\n```", text, re.S)
    assert m, f"no fenced instructions block found in {md_path}"
    return m.group(1).strip()


def tile_by_name(defn, name):
    hits = [a for a in defn["actions"] if isinstance(a, dict) and a.get("name") == name]
    assert len(hits) == 1, f"expected exactly 1 action named {name!r}, found {len(hits)}"
    assert hits[0].get("type") == "TextGeneration", \
        f"action {name!r} is type {hits[0].get('type')!r}, not TextGeneration"
    return hits[0]


def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def main():
    # 1. live definition + backup
    _, live = req(BASE)
    json.dump(live, open(BACKUP, "w"), ensure_ascii=False)
    n_actions = len(live["actions"])
    ids_before = {a.get("id") for a in live["actions"]}
    gui_before = canon(live.get("gui"))
    print(f"live dataflow {DATAFLOW_ID}: actions={n_actions}  backup={BACKUP}")

    # 2-3. swap instructions on each named tile
    targets = set()
    for name, md in TILES:
        new_instr = extract_instructions(md)
        t = tile_by_name(live, name)
        print(f"  [{name}] instr {len(t['instructions'])} -> {len(new_instr)} chars (from {md})")
        t["instructions"] = new_instr
        targets.add(name)

    # per-tile non-instruction snapshots (must be untouched by the round-trip)
    others_before = {n: canon({k: v for k, v in tile_by_name(live, n).items() if k != "instructions"})
                     for n in targets}
    new_instr_by = {n: tile_by_name(live, n)["instructions"] for n in targets}

    # 4. PUT
    try:
        st, _ = req(BASE, method="PUT", body=live)
        print(f"PUT definition -> HTTP {st}")
    except urllib.error.HTTPError as e:
        print(f"PUT FAILED HTTP {e.code}: {e.read().decode()[:300]}")
        sys.exit(1)

    # 5. GET back + strict verify against the ORIGINAL (backup)
    _, back = req(BASE)
    ids_after = {a.get("id") for a in back["actions"]}
    bak = json.load(open(BACKUP))
    diff_vs_orig = [a.get("name") for a in back["actions"]
                    if canon(a) != canon(next((x for x in bak["actions"] if x.get("id") == a.get("id")), None))]
    good = True
    if len(back["actions"]) != n_actions or ids_after != ids_before:
        good = False
    if set(diff_vs_orig) != targets:
        good = False
    for n in targets:
        t = tile_by_name(back, n)
        if t["instructions"] != new_instr_by[n]:
            good = False
        if canon({k: v for k, v in t.items() if k != "instructions"}) != others_before[n]:
            good = False
    if canon(back.get("gui")) != gui_before:
        good = False
    print(f"verify: actions={len(back['actions'])}(want {n_actions}) "
          f"ids_ok={ids_after == ids_before} changed_vs_original={sorted(diff_vs_orig)} "
          f"(want {sorted(targets)}) gui_untouched={canon(back.get('gui')) == gui_before}")

    if not good:
        print("VERIFY FAILED — restoring backup and aborting")
        try:
            req(BASE, method="PUT", body=bak)
            print("restored backup")
        except Exception as e:
            print(f"RESTORE FAILED: {e} — backup at {BACKUP}")
        sys.exit(2)
    print("verify OK — edit was surgical")

    # 6. optional re-run
    if DO_RUN:
        st, ex = req(f"{BASE}/executions", method="POST", body={})
        print(f"triggered execution -> HTTP {st} id={(ex or {}).get('id')} "
              f"state={(ex or {}).get('state')}")
        print(f"EXECUTION={(ex or {}).get('id')}")
    else:
        print("deployed. Set RUN=1 to also trigger a re-run (regenerates the AI columns).")


if __name__ == "__main__":
    main()
