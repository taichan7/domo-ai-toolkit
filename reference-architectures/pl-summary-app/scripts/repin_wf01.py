#!/usr/bin/env python3
"""Re-pin WF-01's SUB_FLOW child-workflow versions and release a new WF-01 version.

WF-01 pins the exact WF-02 / WF-03 versions it calls via each SUB_FLOW node's
data.modelVersion. When a child workflow is bumped, WF-01 must be re-pinned or it
keeps calling the old child version.

Safe pattern (same as deploy_wf_prompt.py):
  1. GET current released WF-01 definition
  2. Rewrite data.modelVersion on the SUB_FLOW node(s) matching the given modelId(s)
  3. POST /versions {"version": TARGET} -> create draft
  4. PUT  /versions/{draft}/definition
  5. GET  /versions/{draft}/definition -> verify (element count unchanged, versions applied)
  6. POST /versions/{draft}/release   (only if RELEASE=1 and verify passed)

Env: INSTANCE, SID, RELEASE=1 to release.
Args: WF01_MODEL_ID  RELEASED_VERSION  TARGET_VERSION  MODELID=VERSION [MODELID=VERSION ...]
"""
import json, os, sys, urllib.request, urllib.error

INSTANCE = os.environ["INSTANCE"]
SID = os.environ["SID"]
MODEL_ID = sys.argv[1]
RELEASED_VERSION = sys.argv[2]
TARGET_VERSION = sys.argv[3]
PINS = dict(kv.split("=", 1) for kv in sys.argv[4:])  # child modelId -> new version
DO_RELEASE = os.environ.get("RELEASE") == "1"

BASE = f"https://{INSTANCE}/api/workflow/v2/models/{MODEL_ID}"
HDR = {"X-Domo-Authentication": SID, "Content-Type": "application/json"}


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=HDR)
    with urllib.request.urlopen(r, timeout=90) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def subflows(defn):
    return [e for e in defn["designElements"] if e.get("type") == "SUB_FLOW"]


def main():
    _, live = req(f"{BASE}/versions/{RELEASED_VERSION}/definition")
    n_de = len(live["designElements"])
    before = {}
    for e in subflows(live):
        mid = e["data"].get("modelId")
        before[mid] = e["data"].get("modelVersion")
    print(f"live v{RELEASED_VERSION}: designElements={n_de} subflows={before}")

    applied = {}
    for e in subflows(live):
        mid = e["data"].get("modelId")
        if mid in PINS:
            e["data"]["modelVersion"] = PINS[mid]
            applied[mid] = PINS[mid]
    missing = set(PINS) - set(applied)
    assert not missing, f"SUB_FLOW nodes not found for modelIds: {missing}"
    print(f"applied pins: {applied}")

    _, draft = req(f"{BASE}/versions", method="POST", body={"version": TARGET_VERSION})
    dv = draft["version"]
    assert dv == TARGET_VERSION, f"draft version {dv} != {TARGET_VERSION}"
    assert draft.get("active") is False
    print(f"created draft v{dv} (active={draft.get('active')})")

    try:
        st, _ = req(f"{BASE}/versions/{dv}/definition", method="PUT", body=live)
        print(f"PUT definition -> HTTP {st}")
    except urllib.error.HTTPError as ex:
        print(f"PUT FAILED HTTP {ex.code}: {ex.read().decode()[:300]}")
        try:
            req(f"{BASE}/versions/{dv}", method="DELETE")
            print(f"cleaned up draft v{dv}")
        except Exception:
            pass
        sys.exit(1)

    _, back = req(f"{BASE}/versions/{dv}/definition")
    b_de = len(back["designElements"])
    got = {e["data"].get("modelId"): e["data"].get("modelVersion") for e in subflows(back)}
    ok = (b_de == n_de) and all(got.get(m) == v for m, v in PINS.items())
    print(f"verify draft v{dv}: designElements={b_de}(want {n_de}) subflows={got} ok={ok}")
    if not ok:
        print("VERIFY FAILED — leaving draft for inspection, NOT releasing")
        sys.exit(2)

    if not DO_RELEASE:
        print(f"draft v{dv} verified. Set RELEASE=1 to release.")
        print(f"DRAFT={dv}")
        return

    st, rel = req(f"{BASE}/versions/{dv}/release", method="POST", body={})
    rel_version = (rel or {}).get("version", dv)
    print(f"release -> HTTP {st} version={rel_version} active={(rel or {}).get('active')}")
    print(f"RELEASED={rel_version}")


if __name__ == "__main__":
    main()
