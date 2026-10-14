#!/usr/bin/env python3
"""Deploy a Python source file to a Domo Code Engine package via REST v2.

Why this exists: Code Engine packages can be created and released entirely via
API, but the version contract is fiddly (verified against the live package):
  - A new version is a POST to /versions whose body carries an explicit semver
    `version`, the `code` source, the declared `functions`, and `configuration`.
    Domo re-parses functions from the code, but the `functions` declaration must
    still be present so the signature (inputs/output) is preserved.
  - POST creates a DRAFT version; it must be released separately (POST .../release).
  - A `version` string that collides with a previously soft-deleted version
    returns HTTP 500 (not a clean 409). Always pick a fresh, never-used semver.

Modes:
  create  NAME  DESCRIPTION  CODE_FILE  "fnName:fnDesc"        -> new package, v1.0.0
  version PACKAGE_ID  CODE_FILE  TARGET_VERSION                -> new version on existing pkg
Env: INSTANCE, SID (set via `domo login` + the session-SID helper in docs/setup-guide.md), RELEASE=1 to release after create.

The function is declared with a single `collection_id` text input and an object
output - matching dedupe_appdb_documents. Adjust fn_object for other signatures.
"""
import hashlib, json, os, sys, urllib.request, urllib.error

INSTANCE = os.environ["INSTANCE"]
SID = os.environ["SID"]
DO_RELEASE = os.environ.get("RELEASE") == "1"
BASE = f"https://{INSTANCE}/api/codeengine/v2/packages"
HDR = {"X-Domo-Authentication": SID, "Content-Type": "application/json"}


def req(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=HDR)
    with urllib.request.urlopen(r, timeout=90) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def fn_object(name, desc):
    return {
        "name": name, "displayName": name, "description": desc, "isPrivate": False,
        "inputs": [{"name": "collection_id", "displayName": "collection_id",
                    "type": "text", "value": None, "nullable": False,
                    "isList": False, "children": [], "entitySubType": None}],
        "output": {"name": "result", "displayName": "result", "type": "object",
                   "value": None, "nullable": True, "isList": False,
                   "children": [], "entitySubType": None},
    }


def release(pkg_id, version):
    st, rel = req(f"{BASE}/{pkg_id}/versions/{version}/release", method="POST", body={})
    print(f"release v{version} -> HTTP {st} releasedOn={(rel or {}).get('releasedOn')}")


def main():
    mode = sys.argv[1]
    if mode == "create":
        name, desc, code_file, fnspec = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        fn_name, fn_desc = fnspec.split(":", 1)
        code = open(code_file, encoding="utf-8").read()
        body = {"name": name, "description": desc, "language": "PYTHON",
                "environment": "LAMBDA", "code": code,
                "manifest": {"functions": [fn_object(fn_name, fn_desc)]}}
        st, r = req(BASE, method="POST", body=body)
        pkg_id = (r or {}).get("id")
        version = (r or {}).get("version", "1.0.0")
        print(f"create -> HTTP {st} packageId={pkg_id} version={version}")
        if DO_RELEASE and pkg_id:
            release(pkg_id, version)
    elif mode == "version":
        pkg_id, code_file, version = sys.argv[2], sys.argv[3], sys.argv[4]
        code = open(code_file, encoding="utf-8").read()
        # Preserve the signature + configuration from the LATEST released version.
        # (Do NOT GET versions/{version} - the target version does not exist yet.)
        _, latest = req(f"{BASE}/{pkg_id}/versions/latest?parts=code,functions,configuration,manifest")
        fns = (latest or {}).get("functions") or ((latest or {}).get("manifest", {}) or {}).get("functions")
        config = (latest or {}).get("configuration") or {
            "accountsMapping": [], "mlModel": [], "externalPackageMapping": {}}
        assert fns, "could not read existing function declarations from latest version"
        print(f"base=latest v{(latest or {}).get('version')} fn={fns[0]['name']}")
        # New version: explicit unique semver + code + functions + configuration.
        body = {"version": version, "code": code, "functions": fns, "configuration": config}
        st, r = req(f"{BASE}/{pkg_id}/versions", method="POST", body=body)
        v = (r or {}).get("version", version)
        print(f"version -> HTTP {st} version={v}")
        if DO_RELEASE:
            release(pkg_id, v)
            # verify the served code is byte-identical to what we sent
            _, got = req(f"{BASE}/{pkg_id}/versions/{v}?parts=code,functions")
            served = (got or {}).get("code") or ""
            same = hashlib.sha256(code.encode()).hexdigest() == hashlib.sha256(served.encode()).hexdigest()
            got_fns = (got or {}).get("functions") or ((got or {}).get("manifest", {}) or {}).get("functions")
            print(f"served code sha == local: {same} | fn preserved: "
                  f"{bool(got_fns) and got_fns[0]['name'] == fns[0]['name']}")
    else:
        print("usage: create ... | version ..."); sys.exit(1)


if __name__ == "__main__":
    main()
