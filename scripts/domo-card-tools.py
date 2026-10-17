#!/usr/bin/env python3
"""Query the catalog, inspect definitions, or verify native card rendering.

Inspection reads definitions, despite the retrieval endpoint using PUT. It never
calls card save/copy/delete. Rendering reads query results; reports omit row values.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CATALOG = Path(__file__).resolve().parents[1] / "docs/reference/domo-card-config-catalog.json"
HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.domo\.com")
CARD_URN = re.compile(r"(?:[0-9]+|dr:[0-9]+:[0-9]+)")


def page_id(value: str, instance: str) -> str:
    if re.fullmatch(r"[0-9]+", value):
        return value
    u = urlparse(value)
    match = re.fullmatch(r"/page/([0-9]+)/?", u.path)
    if (u.scheme != "https" or u.netloc != instance or not match
            or u.query or u.fragment or u.username or u.password):
        raise ValueError("Use a page ID or an HTTPS /page/<id> URL on the selected instance")
    return match.group(1)


def count_list(value) -> int:
    return len(value) if isinstance(value, list) else 0


def summarize_definition(raw: dict) -> dict:
    """Allowlisted structure only: no column names, formulas, values, or titles."""
    if not isinstance(raw, dict):
        raise ValueError("Expected a definition response object")
    definition = raw.get("definition")
    if not isinstance(definition, dict):
        raise ValueError("Missing definition object")
    charts = definition.get("charts")
    main = charts.get("main") if isinstance(charts, dict) else None
    chart_type = main.get("chartType") if isinstance(main, dict) else None
    if not isinstance(chart_type, str) or not re.fullmatch(r"badge_[a-z0-9_]+", chart_type):
        raise ValueError("Missing standard-card chart type")
    subscriptions = definition.get("subscriptions")
    if not isinstance(subscriptions, dict) or not isinstance(subscriptions.get("main"), dict):
        raise ValueError("Missing main subscription")
    result = {"chart_type": chart_type, "subscriptions": {}}
    version = definition.get("chartVersion")
    if isinstance(version, int) or (isinstance(version, str) and version.isdigit()):
        result["chart_version"] = version
    for name in ("main", "big_number"):
        sub = subscriptions.get(name)
        if not isinstance(sub, dict):
            continue
        cols = sub.get("columns", [])
        if not isinstance(cols, list) or any(not isinstance(c, dict) for c in cols):
            raise ValueError("Invalid subscription columns")
        # Fixed vocabulary prevents caller-controlled content entering the report.
        known_roles = {"ITEM", "VALUE", "SERIES", "TARGET", "XTIME", "CATEGORY",
                       "CURRENT", "COLUMN", "ROW", "BUBBLESIZE", "START_DATE",
                       "END_DATE", "HIGH", "LOW", "RANGE1", "RANGE2", "RANGE3",
                       "DATE", "EVENT", "VALUE1", "GROUP1", "GROUP2", "SEGMENTS",
                       "COLOR", "LOWER", "MEDIAN", "UPPER", "MAX",
                       "EXTRAINFO1", "EXTRAINFO2", "EXTRAINFO3"}
        roles = Counter(c.get("mapping") if c.get("mapping") in known_roles
                        else "UNMAPPED_OR_OTHER" for c in cols)
        aggs = Counter(c.get("aggregation") if c.get("aggregation") in
                       {"SUM", "COUNT", "AVG", "MIN", "MAX"} else "NONE_OR_OTHER" for c in cols)
        result["subscriptions"][name] = {
            "column_count": len(cols), "roles": dict(sorted(roles.items())),
            "aggregations": dict(sorted(aggs.items())),
            "formula_reference_count": sum(bool(c.get("formulaId")) for c in cols),
            "formatted_column_count": sum(bool(c.get("format")) for c in cols),
            "filter_count": count_list(sub.get("filters")),
            "group_by_count": count_list(sub.get("groupBy")),
            "order_by_count": count_list(sub.get("orderBy")),
            "has_date_grain": bool(sub.get("dateGrain")),
            "has_date_range_filter": bool(sub.get("dateRangeFilter")),
        }
    overrides = main.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("Invalid chart overrides")
    result["override_keys"] = sorted(k for k in overrides
                                     if re.fullmatch(r"[a-z][a-z0-9_]*", k))
    result["conditional_format_count"] = count_list(definition.get("conditionalFormats"))
    result["annotation_count"] = count_list(definition.get("annotations"))
    result["control_count"] = count_list(definition.get("controls"))
    result["formula_definition_count"] = count_list(definition.get("formulas"))
    # The outer drillpath lists ancestors, not descendants of the requested card.
    result["drill_ancestor_count"] = count_list(raw.get("drillpath"))
    return result


def summarize_render(raw: dict, expected_dataset: str | None = None) -> dict:
    """Validate the observed named-parts response without exposing any data values."""
    if not isinstance(raw, dict):
        raise ValueError("Expected named render parts")
    image_part = raw.get("image")
    img = image_part.get("data") if isinstance(image_part, dict) else None
    if not isinstance(img, str):
        raise ValueError("Missing native image")
    try:
        decoded = base64.b64decode(img.split(",", 1)[-1], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid image encoding") from None
    if not decoded.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected a native PNG image")
    qr = raw.get("queryResult")
    data = qr.get("data") if isinstance(qr, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("Missing structured query result")
    rows = data["rows"]
    if data.get("numRows") != len(rows):
        raise ValueError("Inconsistent query row count")
    if expected_dataset and data.get("datasource") != expected_dataset:
        raise ValueError("Rendered query uses an unexpected dataset")
    known_types = {"STRING", "LONG", "DOUBLE", "DECIMAL", "DATE", "DATETIME", "BOOLEAN"}
    return {"png_bytes": len(decoded), "returned_rows": len(rows),
            "column_types": [m.get("type") if m.get("type") in known_types else "OTHER"
                             for m in data.get("metadata", [])],
            "limited": raw.get("limited"), "query_limited": qr.get("limited"),
            "not_all_data_shown": raw.get("notAllDataShown"),
            "image_not_all_data_shown": raw.get("image", {}).get("notAllDataShown"),
            "expected_dataset_checked": bool(expected_dataset)}


class Client:
    def __init__(self, instance: str):
        if not HOST.fullmatch(instance):
            raise ValueError("Specify a Domo instance hostname, without a URL or path")
        selected = os.environ.get("INSTANCE")
        if selected and selected != instance:
            raise ValueError("INSTANCE differs from --instance; select matching credentials")
        token, sid = os.environ.get("DOMO_TOKEN"), os.environ.get("SID")
        if not token and not sid:
            raise ValueError("Export INSTANCE and DOMO_TOKEN or SID; see the authentication helper")
        self.base = "https://" + instance
        self.headers = ({"X-DOMO-Developer-Token": token} if token
                        else {"X-Domo-Authentication": sid})

    def request(self, path: str, body=None):
        # Allowlist retrieval/rendering only. No save, copy, or delete operations.
        if body is None:
            if not re.fullmatch(r"/api/content/v1/pages/[0-9]+/cards", path):
                raise ValueError("Unsupported retrieval path")
            method, data = "GET", None
        else:
            if path == "/api/content/v3/cards/kpi/definition":
                if (set(body) != {"dynamicText", "variables", "urn"}
                    or body["dynamicText"] is not True or body["variables"] is not True
                    or not CARD_URN.fullmatch(str(body["urn"]))):
                    raise ValueError("Invalid definition read request")
            elif re.fullmatch(r"/api/content/v1/cards/kpi/(?:[0-9]+|dr:[0-9]+:[0-9]+)/render\?parts=image,queryResult", path):
                if (set(body) != {"width", "height"}
                        or any(type(body[k]) is not int or not 1 <= body[k] <= 8192
                               for k in ("width", "height"))):
                    raise ValueError("Rendering requires bounded integer width and height")
            else:
                raise ValueError("Unsupported retrieval path")
            method, data = "PUT", json.dumps(body).encode()
        req = Request(self.base + path, data=data, method=method,
                      headers={**self.headers, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=45) as response:
                return json.load(response)
        except HTTPError as exc:
            # Response bodies and headers may contain sensitive details.
            raise RuntimeError(f"HTTP {exc.code} during {method} retrieval") from None
        except (URLError, TimeoutError):
            raise RuntimeError("Network error during card retrieval") from None


def inspect(client, pages: list[str], cards: list[str]) -> dict:
    selected = set(cards)
    page_reports = []
    for pid in dict.fromkeys(pages):
        entries = client.request(f"/api/content/v1/pages/{pid}/cards")
        if not isinstance(entries, list):
            raise ValueError("Unexpected page cards response")
        if any(not isinstance(c, dict) or (c.get("type") == "kpi" and "urn" not in c)
               for c in entries):
            raise ValueError("Invalid page card entry")
        kpis = [str(c["urn"]) for c in entries if c.get("type") == "kpi"]
        if any(not re.fullmatch(r"[0-9]+", cid) for cid in kpis):
            raise ValueError("Invalid card identifier")
        selected.update(kpis)
        page_reports.append({"page_id": pid, "total": len(entries),
                             "standard": len(kpis), "other": len(entries) - len(kpis),
                             "card_ids": kpis})
    results, failures = [], []
    for cid in sorted(selected, key=lambda s: [int(p) for p in s.replace("dr:", "").split(":")]):
        try:
            raw = client.request("/api/content/v3/cards/kpi/definition",
                                 {"dynamicText": True, "variables": True, "urn": cid})
            results.append({"card_id": cid, **summarize_definition(raw)})
        except (RuntimeError, ValueError, KeyError, TypeError):
            failures.append({"card_id": cid, "error": "Definition unavailable or unsupported"})
    return {"schema_version": 1, "pages": page_reports, "cards": results,
            "chart_type_count": len({c["chart_type"] for c in results}),
            "override_key_count": len({k for c in results for k in c["override_keys"]}),
            "failures": failures}


def lookup(catalog: dict, chart: str | None, search: str, prop: str) -> dict:
    charts = catalog["chart_types"]
    if chart:
        if chart not in charts:
            raise ValueError("Chart not in this study; absence does not mean Domo lacks it")
        c = charts[chart]
        properties = [catalog["properties"][p] for p in c["property_refs"]]
        if prop:
            properties = [p for p in properties if prop.lower() in
                          (p["key"] + " " + p["label"] + " " + p["category"]).lower()]
        return {"chart_type": chart, **{k: v for k, v in c.items() if k != "property_refs"},
                "property_schemas": properties}
    return {k: {"name": c["name"], "live_card_count": c["live_card_count"]}
            for k, c in charts.items() if search.lower() in (k + " " + c["name"]).lower()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalog", help="Offline chart roles and property schemas")
    cat.add_argument("chart", nargs="?")
    cat.add_argument("--search", default="")
    cat.add_argument("--property", default="")
    for command, help_text in [("inspect", "Read selected definitions"),
                               ("verify", "Read definitions and render native PNG/query results")]:
        live = sub.add_parser(command, help=help_text)
        live.add_argument("--instance", default=os.environ.get("INSTANCE"))
        live.add_argument("--page", action="append", default=[])
        live.add_argument("--card", action="append", default=[])
        if command == "verify":
            live.add_argument("--width", type=int, default=900)
            live.add_argument("--height", type=int, default=600)
            live.add_argument("--expected-dataset")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            if args.property and not args.chart:
                raise ValueError("--property requires a chart code")
            report = lookup(json.loads(CATALOG.read_text()), args.chart, args.search, args.property)
            status = 0
        else:
            if not args.page and not args.card:
                raise ValueError("Specify at least one --page or --card")
            if any(not CARD_URN.fullmatch(cid) for cid in args.card):
                raise ValueError("Use numeric card IDs or dr:<viewId>:<rootCardId> URNs")
            client = Client(args.instance or "")
            report = inspect(client, [page_id(p, args.instance) for p in args.page], args.card)
            if args.command == "verify":
                for card in report["cards"]:
                    cid = card["card_id"]
                    try:
                        raw = client.request(f"/api/content/v1/cards/kpi/{cid}/render?parts=image,queryResult",
                                             {"width": args.width, "height": args.height})
                        card["render"] = summarize_render(raw, args.expected_dataset)
                    except (RuntimeError, ValueError, KeyError, TypeError):
                        report["failures"].append({"card_id": cid, "error": "Native render verification failed"})
            status = 1 if report["failures"] else 0
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return status
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
