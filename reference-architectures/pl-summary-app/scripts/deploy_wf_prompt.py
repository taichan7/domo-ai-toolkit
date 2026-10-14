#!/usr/bin/env python3
"""Deploy an updated AI system prompt to a Domo Workflow model via REST.

Flow (released versions are immutable, so we must create a fresh draft):
  1. GET the current released definition (highest released version)
  2. Build instructions from the canonical .md (strip the leading blockquote note)
  3. Swap ONLY designElements[AI_AGENT].data.agent.instructions
  4. POST /versions {"version": TARGET_VERSION}  -> create draft with that semver
  5. PUT  /versions/{d}/definition  <- full modified definition (allowed on drafts)
  6. GET  /versions/{d}/definition  -> verify round-trip
  7. POST /versions/{d}/release -> release; capture the assigned version

Env: INSTANCE, SID (set via `domo login` + the session-SID helper in docs/setup-guide.md), RELEASE=1 to actually release.
Args: MODEL_ID  RELEASED_VERSION  PROMPT_MD  TARGET_VERSION
Prints the released version number on the last line as: RELEASED=<version>
"""
import json, os, sys, re, urllib.request, urllib.error

INSTANCE = os.environ["INSTANCE"]
SID = os.environ["SID"]
MODEL_ID = sys.argv[1]
RELEASED_VERSION = sys.argv[2]
PROMPT_MD = sys.argv[3]
TARGET_VERSION = sys.argv[4]  # semver string to create, e.g. "1.0.9"
DO_RELEASE = os.environ.get("RELEASE") == "1"

BASE = f"https://{INSTANCE}/api/workflow/v2/models/{MODEL_ID}"
HDR = {"X-Domo-Authentication": SID, "Content-Type": "application/json"}


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=HDR)
    with urllib.request.urlopen(r, timeout=90) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def build_instructions(md_path):
    """Canonical .md -> system prompt string. Strip leading blockquote note lines."""
    text = open(md_path, encoding="utf-8").read()
    lines = text.splitlines()
    kept = [ln for ln in lines if not ln.lstrip().startswith(">")]
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
    return out


def ai_node(defn):
    ais = [e for e in defn["designElements"] if e.get("type") == "AI_AGENT"]
    assert len(ais) == 1, f"expected exactly 1 AI_AGENT node, found {len(ais)}"
    return ais[0]


def main():
    # 1. live released definition
    _, live = req(f"{BASE}/versions/{RELEASED_VERSION}/definition")
    n_de = len(live["designElements"])
    live_ai = ai_node(live)
    old_instr = live_ai["data"]["agent"]["instructions"]
    prompt_value_before = ((live_ai.get("data") or {}).get("prompt") or {}).get("value")
    print(f"live v{RELEASED_VERSION}: designElements={n_de} instr_len={len(old_instr)} "
          f"prompt.value_len={len(prompt_value_before or '')}")

    # 2-3. swap instructions only
    new_instr = build_instructions(PROMPT_MD)
    live_ai["data"]["agent"]["instructions"] = new_instr
    print(f"new instructions len={len(new_instr)} (from {PROMPT_MD})")

    # 4. create draft with the explicit target semver (POST respects a STRING
    #    version; an int maps to "0.0.N"). The definition content is NOT
    #    persisted by POST; it must be PUT afterwards.
    _, draft = req(f"{BASE}/versions", method="POST", body={"version": TARGET_VERSION})
    dv = draft["version"]
    assert dv == TARGET_VERSION, f"draft version {dv} != requested {TARGET_VERSION}"
    assert draft.get("active") is False, "new draft should be inactive"
    print(f"created draft v{dv} (active={draft.get('active')})")

    # 5. PUT modified definition into the draft
    try:
        st, _ = req(f"{BASE}/versions/{dv}/definition", method="PUT", body=live)
        print(f"PUT definition -> HTTP {st}")
    except urllib.error.HTTPError as e:
        print(f"PUT FAILED HTTP {e.code}: {e.read().decode()[:300]}")
        # clean up the draft so we don't leave garbage
        try:
            req(f"{BASE}/versions/{dv}", method="DELETE")
            print(f"cleaned up draft v{dv}")
        except Exception:
            pass
        sys.exit(1)

    # 6. verify round-trip
    _, back = req(f"{BASE}/versions/{dv}/definition")
    b_de = len(back["designElements"])
    b_ai = ai_node(back)
    b_instr = b_ai["data"]["agent"]["instructions"]
    b_prompt_value = ((b_ai.get("data") or {}).get("prompt") or {}).get("value")
    ok = (b_de == n_de and b_instr == new_instr and b_prompt_value == prompt_value_before)
    print(f"verify draft v{dv}: designElements={b_de}(want {n_de}) "
          f"instr_match={b_instr == new_instr} prompt.value_untouched={b_prompt_value == prompt_value_before}")
    if not ok:
        print("VERIFY FAILED — leaving draft in place for inspection, NOT releasing")
        sys.exit(2)

    if not DO_RELEASE:
        print(f"draft v{dv} verified. Set RELEASE=1 to release.")
        print(f"DRAFT={dv}")
        return

    # 7. release
    st, rel = req(f"{BASE}/versions/{dv}/release", method="POST", body={})
    rel_version = (rel or {}).get("version", dv)
    print(f"release -> HTTP {st} version={rel_version} active={(rel or {}).get('active')}")
    print(f"RELEASED={rel_version}")


if __name__ == "__main__":
    main()
