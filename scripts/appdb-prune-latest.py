#!/usr/bin/env python3
"""Prune an AppDB collection.

Two retention modes (mutually exclusive):

- ``--keep N``      keep the newest N documents (count mode; default N=10)
- ``--keep-days D`` keep every document inside the last D days and delete
                    only documents older than that window (day mode)

Day mode keeps documents whose ``createdOn`` is missing/invalid (unknown age
is never a delete reason). Default mode is dry-run. Real deletes require both
--execute and --confirmed. The script avoids printing tokens, SIDs, or
refresh tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any


DEFAULT_LIMIT = 100
DEFAULT_CONCURRENCY = 10
DEFAULT_ENFORCE_PASSES = 3
DEFAULT_SETTLE_SECONDS = 5.0

# 欠損/不正なタイムスタンプの番兵（最古）。datetime は不変なので
# モジュール定数として 1 度だけ生成すれば毎回の生成と等価。parse_dt が
# 「並べ替えの最後 = 最も古い」へ倒すために使う。
_MIN_DT = datetime.min.replace(tzinfo=timezone.utc)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_collection_url(url: str) -> tuple[str, str]:
    match = re.match(r"^https://([^/]+)/appDb/([^/]+)/dataexplorer/?$", url.strip())
    if not match:
        raise ValueError(
            "collection URL must look like "
            "https://<instance>/appDb/<collectionId>/dataexplorer"
        )
    return match.group(1), match.group(2)


def parse_dt(value: Any) -> datetime:
    if not value:
        return _MIN_DT
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            # 範囲外/不正な数値エポックは、文字列分岐と同じく最古へ倒す。
            # なぜ: このモジュールの契約は「欠損/不正 → _MIN_DT」で、sort_docs は
            # 取得した全ドキュメントに parse_dt を通す。ここで例外を送出すると
            # 1 件の壊れた数値タイムスタンプが prune/検証フェッチ全体を巻き添えに
            # して落とす（削除後の検証フェッチで落ちると残数の要約すら出ない）。
            return _MIN_DT
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return _MIN_DT
    return _MIN_DT


def sort_docs(docs: list[dict[str, Any]], sort_field: str) -> list[dict[str, Any]]:
    return sorted(
        docs,
        key=lambda d: (parse_dt(d.get(sort_field)), str(d.get("id", ""))),
        reverse=True,
    )


@dataclass
class AuthContext:
    instance: str
    source: str
    header_name: str
    secret: str
    session_file: Path | None
    lock: Lock

    def headers(self) -> dict[str, str]:
        with self.lock:
            secret = self.secret
        return {
            self.header_name: secret,
            "Accept": "application/json",
        }

    def refresh_sid(self) -> None:
        if self.header_name != "X-Domo-Authentication":
            raise RuntimeError("cannot refresh non-SID authentication")

        config = Path.home() / ".config" / "configstore" / "ryuu" / f"{self.instance}.json"
        if not config.exists():
            raise RuntimeError(
                f"ryuu config not found for {self.instance}; run domo login -i {self.instance}"
            )
        refresh_token = json.loads(config.read_text()).get("refreshToken")
        if not refresh_token:
            raise RuntimeError(
                f"refreshToken missing in ryuu config for {self.instance}; run domo login -i {self.instance}"
            )

        body = urllib.parse.urlencode(
            {
                "client_id": "domo:internal:devstudio",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode("utf-8")
        token_req = urllib.request.Request(
            f"https://{self.instance}/api/oauth2/token",
            data=body,
            method="POST",
            headers={"content-type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        with urllib.request.urlopen(token_req, timeout=60) as resp:
            access_token = json.loads(resp.read()).get("access_token")
        if not access_token:
            raise RuntimeError("access_token missing during SID refresh")

        sid_req = urllib.request.Request(
            f"https://{self.instance}/api/oauth2/sid",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(sid_req, timeout=60) as resp:
            sid = json.loads(resp.read()).get("sid")
        if not sid:
            raise RuntimeError("sid missing during SID refresh")

        with self.lock:
            self.secret = sid
        if self.session_file:
            self.session_file.write_text(f"INSTANCE={self.instance}\nSID={sid}\n")
        print("Refreshed Domo SID without printing it.", flush=True)


def read_session_file(path: Path, instance: str) -> str | None:
    if not path.exists():
        return None
    found_instance = ""
    sid = ""
    for line in path.read_text().splitlines():
        if line.startswith("INSTANCE="):
            found_instance = line.split("=", 1)[1].strip()
        elif line.startswith("SID="):
            sid = line.split("=", 1)[1].strip()
    if found_instance == instance and sid:
        return sid
    return None


def load_auth(instance: str) -> AuthContext:
    env_instance = os.environ.get("INSTANCE", "")
    env_token = os.environ.get("DOMO_TOKEN", "")
    env_sid = os.environ.get("SID", "")

    if env_token and (not env_instance or env_instance == instance):
        return AuthContext(
            instance=instance,
            source="INSTANCE + DOMO_TOKEN",
            header_name="X-DOMO-Developer-Token",
            secret=env_token,
            session_file=None,
            lock=Lock(),
        )

    if env_sid and (not env_instance or env_instance == instance):
        return AuthContext(
            instance=instance,
            source="INSTANCE + SID",
            header_name="X-Domo-Authentication",
            secret=env_sid,
            session_file=None,
            lock=Lock(),
        )

    session_candidates = []
    if os.environ.get("DOMO_SESSION_FILE"):
        session_candidates.append(Path(os.environ["DOMO_SESSION_FILE"]))
    session_candidates.extend(
        [
            repo_root() / "ai" / "scripts" / ".sid",
            repo_root() / ".sid",
        ]
    )

    for session_file in session_candidates:
        sid = read_session_file(session_file, instance)
        if sid:
            return AuthContext(
                instance=instance,
                source=f"session file {session_file}",
                header_name="X-Domo-Authentication",
                secret=sid,
                session_file=session_file,
                lock=Lock(),
            )

    raise RuntimeError(
        "No Domo auth found. Set INSTANCE + DOMO_TOKEN, set INSTANCE + SID, "
        "or run bash scripts/authenticate.sh <instance>."
    )


class AppDBClient:
    def __init__(self, auth: AuthContext, collection_id: str, limit: int) -> None:
        self.auth = auth
        self.collection_id = collection_id
        self.limit = limit
        self.base_url = (
            f"https://{auth.instance}/api/datastores/v2/collections/"
            f"{collection_id}/documents"
        )

    def request_json(self, url: str, method: str = "GET", attempts: int = 5) -> Any:
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(url, method=method, headers=self.auth.headers())
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    body = resp.read()
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:500]
                if exc.code == 401 and attempt == 1:
                    self.auth.refresh_sid()
                    continue
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts:
                    time.sleep(min(20, attempt * 3))
                    continue
                raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
            except Exception:
                if attempt < attempts:
                    time.sleep(min(20, attempt * 3))
                    continue
                raise
        raise RuntimeError(f"failed requesting {url}")

    def smoke_test(self) -> None:
        url = f"https://{self.auth.instance}/api/data/v3/datasources?limit=1"
        smoke = self.request_json(url)
        if not isinstance(smoke, dict) or "dataSources" not in smoke:
            raise RuntimeError("smoke test failed; unexpected datasources response")

    def fetch_all_docs(self, sort_field: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = self.request_json(f"{self.base_url}?limit={self.limit}&offset={offset}")
            if isinstance(batch, dict):
                for key in ("documents", "items", "data"):
                    if key in batch and isinstance(batch[key], list):
                        batch = batch[key]
                        break
            if not isinstance(batch, list):
                raise RuntimeError(
                    f"unexpected document list response shape: {type(batch).__name__}"
                )
            if not batch:
                break
            docs.extend(batch)
            if len(batch) < self.limit:
                break
            offset += self.limit
        return sort_docs(docs, sort_field)

    def delete_doc(self, doc_id: str, attempts: int = 6) -> tuple[str, bool, int | str]:
        url = f"{self.base_url}/{doc_id}"
        for attempt in range(1, attempts + 1):
            req = urllib.request.Request(url, method="DELETE", headers=self.auth.headers())
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    return doc_id, True, resp.status
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt == 1:
                    self.auth.refresh_sid()
                    continue
                if exc.code == 404:
                    return doc_id, True, 404
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts:
                    time.sleep(min(30, attempt * 3))
                    continue
                return doc_id, False, exc.code
            except Exception as exc:
                if attempt < attempts:
                    time.sleep(min(30, attempt * 3))
                    continue
                return doc_id, False, type(exc).__name__
        return doc_id, False, "retry_exhausted"


def date_counts(docs: list[dict[str, Any]], sort_field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for doc in docs:
        dt = parse_dt(doc.get(sort_field))
        key = dt.date().isoformat() if dt.year > 1 else "missing/invalid"
        counts[key] += 1
    return counts


def print_doc_summary(docs: list[dict[str, Any]], sort_field: str, prefix: str = "") -> None:
    if not docs:
        print(f"{prefix}No documents found.")
        return
    oldest = parse_dt(docs[-1].get(sort_field)).isoformat()
    newest = parse_dt(docs[0].get(sort_field)).isoformat()
    print(f"{prefix}{sort_field} UTC range: {oldest} -> {newest}")
    print(f"{prefix}Date counts by {sort_field} UTC:")
    for date, count in sorted(date_counts(docs, sort_field).items()):
        print(f"{prefix}  {date}: {count}")


def split_keep_delete(
    docs: list[dict[str, Any]],
    keep: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    keep_docs = docs[:keep]
    keep_ids = {doc.get("id") for doc in keep_docs}
    # ローカル名は delete_id_list とする（なぜ: モジュール直下の関数 delete_ids() を
    # 関数スコープ内で影に隠す shadow を避ける。呼び出し側 main() も戻り値を
    # delete_ids_initial / extra_ids と命名して同名衝突を回避しており、本関数だけが
    # 例外だった。将来この関数内から削除実行関数 delete_ids() を呼ぶ改修時の誤参照を防ぐ）。
    delete_id_list = [
        doc.get("id")
        for doc in docs[keep:]
        if doc.get("id") and doc.get("id") not in keep_ids
    ]
    return keep_docs, delete_id_list


def select_by_days(
    docs: list[dict[str, Any]],
    cutoff: datetime,
    sort_field: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Day-based retention selection.

    Keeps every document whose timestamp is >= cutoff. Documents whose
    timestamp is missing/invalid are KEPT (unknown age is never a delete
    reason). Returns (keep_docs_newest_first, delete_id_list_oldest_first).
    """
    keep_docs: list[dict[str, Any]] = []
    delete_docs: list[dict[str, Any]] = []
    for doc in docs:
        dt = parse_dt(doc.get(sort_field))
        if dt.year <= 1 or dt >= cutoff:
            keep_docs.append(doc)
        else:
            delete_docs.append(doc)
    keep_docs = sorted(
        keep_docs,
        key=lambda d: (parse_dt(d.get(sort_field)), str(d.get("id", ""))),
        reverse=True,
    )
    delete_docs.sort(key=lambda d: (parse_dt(d.get(sort_field)), str(d.get("id", ""))))
    delete_id_list = [doc.get("id") for doc in delete_docs if doc.get("id")]
    return keep_docs, delete_id_list


def count_older_than(docs: list[dict[str, Any]], cutoff: datetime, sort_field: str) -> int:
    """Count docs (with a known age) strictly older than cutoff."""
    count = 0
    for doc in docs:
        dt = parse_dt(doc.get(sort_field))
        if dt.year > 1 and dt < cutoff:
            count += 1
    return count


def print_keep_and_sample(
    keep_docs: list[dict[str, Any]],
    delete_docs: list[dict[str, Any]],
    sample_size: int,
    sort_field: str,
) -> None:
    print("\nKeep candidates newest first:")
    for index, doc in enumerate(keep_docs, 1):
        print(
            f"  {index:02d}. id={doc.get('id')} "
            f"{sort_field}={doc.get(sort_field)} updatedOn={doc.get('updatedOn')}"
        )

    print("\nDelete candidate sample:")
    if not delete_docs:
        print("  none")
        return

    sample = delete_docs[:sample_size]
    if len(delete_docs) > sample_size * 2:
        sample += delete_docs[-sample_size:]
    else:
        sample = delete_docs

    seen: set[str] = set()
    for doc in sample:
        doc_id = str(doc.get("id"))
        if doc_id in seen:
            continue
        seen.add(doc_id)
        print(
            f"  id={doc.get('id')} "
            f"{sort_field}={doc.get(sort_field)} updatedOn={doc.get('updatedOn')}"
        )


def delete_ids(
    client: AppDBClient,
    doc_ids: list[str],
    concurrency: int,
) -> tuple[int, list[tuple[str, int | str]]]:
    deleted = 0
    failed: list[tuple[str, int | str]] = []
    processed = 0
    last_report = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(client.delete_doc, doc_id) for doc_id in doc_ids]
        for future in as_completed(futures):
            doc_id, ok, status = future.result()
            processed += 1
            if ok:
                deleted += 1
            else:
                failed.append((doc_id, status))
            now = time.monotonic()
            if processed % 100 == 0 or processed == len(doc_ids) or now - last_report >= 30:
                print(
                    f"  processed={processed}/{len(doc_ids)} "
                    f"deleted={deleted} failed={len(failed)}",
                    flush=True,
                )
                last_report = now

    return deleted, failed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or prune an AppDB collection to its latest N documents."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--collection-url", help="Full /appDb/<collectionId>/dataexplorer URL")
    target.add_argument("--collection-id", help="AppDB collection UUID")
    parser.add_argument("--instance", help="Domo instance domain, e.g. maintenance-instance.domo.com")
    parser.add_argument("--collection-name", default="", help="Optional display name for logs")
    retention = parser.add_mutually_exclusive_group()
    retention.add_argument(
        "--keep",
        type=int,
        default=None,
        help="Number of newest docs to keep (count mode; default 10)",
    )
    retention.add_argument(
        "--keep-days",
        type=int,
        default=None,
        help="Retention window in days (day mode; deletes docs older than the window)",
    )
    parser.add_argument("--sort-field", default="createdOn", help="Timestamp field for recency")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="List page size")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Parallel DELETE workers",
    )
    parser.add_argument(
        "--enforce-passes",
        type=int,
        default=DEFAULT_ENFORCE_PASSES,
        help="Extra fetch/delete passes after the first delete batch",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=DEFAULT_SETTLE_SECONDS,
        help="Wait time before verification or enforcement fetches",
    )
    parser.add_argument("--sample-size", type=int, default=5, help="Dry-run sample size")
    parser.add_argument("--execute", action="store_true", help="Actually delete documents")
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Required with --execute after explicit user confirmation",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.collection_url:
        parsed_instance, collection_id = parse_collection_url(args.collection_url)
        instance = args.instance or parsed_instance
        if args.instance and args.instance != parsed_instance:
            raise SystemExit(
                f"ERROR: --instance {args.instance!r} does not match URL host {parsed_instance!r}"
            )
    else:
        if not args.instance:
            raise SystemExit("ERROR: --instance is required with --collection-id")
        instance = args.instance
        collection_id = args.collection_id

    if args.keep is None and args.keep_days is None:
        args.keep = 10
    if args.keep is not None and args.keep < 0:
        raise SystemExit("ERROR: --keep must be >= 0")
    if args.keep_days is not None and args.keep_days < 1:
        raise SystemExit("ERROR: --keep-days must be >= 1")
    day_mode = args.keep_days is not None
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=args.keep_days)
        if day_mode
        else None
    )
    if args.limit <= 0 or args.limit > 100:
        raise SystemExit("ERROR: --limit must be between 1 and 100")
    if args.concurrency <= 0:
        raise SystemExit("ERROR: --concurrency must be >= 1")
    # settle-seconds が負だと、最初の削除バッチ後に呼ぶ time.sleep(args.settle_seconds)
    # が ValueError（sleep length must be non-negative）で落ちる。その時点で一部
    # ドキュメントは既に削除済みなのに検証も要約も出ず異常終了する＝「一部破壊した後に
    # クラッシュ」する最悪の失敗になる。他の数値引数と同じく破壊的操作の前に fail-fast する。
    if args.settle_seconds < 0:
        raise SystemExit("ERROR: --settle-seconds must be >= 0")
    # enforce-passes が負だと range(1, n+1) が空になり、要求した強制削除パスが黙って
    # スキップされる（残存ドキュメントの取りこぼしに気付けない）。0 は「強制パス無し」の
    # 正当な選択なので < 0 のみ弾く。
    if args.enforce_passes < 0:
        raise SystemExit("ERROR: --enforce-passes must be >= 0")
    if args.execute and not args.confirmed:
        raise SystemExit("ERROR: --execute requires --confirmed")

    auth = load_auth(instance)
    client = AppDBClient(auth, collection_id, args.limit)

    label = args.collection_name or collection_id
    print(f"Collection: {label} ({collection_id})")
    print(f"Instance: {instance}")
    print(f"Auth source: {auth.source}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    if day_mode:
        print(f"Retention window: {args.keep_days} days (cutoff {cutoff.isoformat()})")
    else:
        print(f"Keep newest documents: {args.keep}")
    print(f"Sort field: {args.sort_field}")
    print(f"Concurrency: {args.concurrency}")

    client.smoke_test()
    docs = client.fetch_all_docs(args.sort_field)
    if day_mode:
        keep_docs, delete_ids_initial = select_by_days(docs, cutoff, args.sort_field)
        delete_set = set(delete_ids_initial)
        delete_docs = [doc for doc in docs if doc.get("id") in delete_set]
    else:
        keep_docs, delete_ids_initial = split_keep_delete(docs, args.keep)
        delete_docs = docs[args.keep:]

    print(f"\nTotal documents: {len(docs)}")
    print(f"Keep candidates: {len(keep_docs)}")
    print(f"Delete candidates: {len(delete_ids_initial)}")
    print_doc_summary(docs, args.sort_field)
    print_keep_and_sample(keep_docs, delete_docs, args.sample_size, args.sort_field)

    if not args.execute:
        print("\nDry-run only. Re-run with --execute --confirmed after explicit confirmation.")
        return 0

    if not delete_ids_initial:
        print("\nNo delete candidates.")
    else:
        print(f"\nDeleting {len(delete_ids_initial)} documents...", flush=True)
    total_deleted = 0
    failed: list[tuple[str, int | str]] = []
    deleted, batch_failed = delete_ids(client, delete_ids_initial, args.concurrency)
    total_deleted += deleted
    failed.extend(batch_failed)

    if failed:
        print("Stopping enforcement because delete failures occurred.")
    else:
        time.sleep(args.settle_seconds)
        for pass_no in range(1, args.enforce_passes + 1):
            current_docs = client.fetch_all_docs(args.sort_field)
            if day_mode:
                if count_older_than(current_docs, cutoff, args.sort_field) == 0:
                    break
                _, extra_ids = select_by_days(current_docs, cutoff, args.sort_field)
            else:
                if len(current_docs) <= args.keep:
                    break
                _, extra_ids = split_keep_delete(current_docs, args.keep)
            if not extra_ids:
                break
            print(f"Enforcement pass {pass_no}: deleting extra docs={len(extra_ids)}")
            deleted, batch_failed = delete_ids(client, extra_ids, args.concurrency)
            total_deleted += deleted
            failed.extend(batch_failed)
            if batch_failed:
                break
            time.sleep(args.settle_seconds)

    final_docs = client.fetch_all_docs(args.sort_field)

    print("\nVerification:")
    print(f"  Deleted or already gone: {total_deleted}")
    print(f"  Failed deletes: {len(failed)}")
    print(f"  Remaining documents: {len(final_docs)}")
    print_doc_summary(final_docs, args.sort_field, prefix="  ")
    print("  Remaining docs newest first:")
    for index, doc in enumerate(final_docs[: max(args.keep or 0, 20)], 1):
        print(
            f"    {index:02d}. id={doc.get('id')} "
            f"{args.sort_field}={doc.get(args.sort_field)} updatedOn={doc.get('updatedOn')}"
        )

    if failed:
        print("\nFailed delete sample:")
        for doc_id, status in failed[:10]:
            print(f"  id={doc_id} status={status}")
        return 2

    if day_mode:
        remaining_old = count_older_than(final_docs, cutoff, args.sort_field)
        if remaining_old:
            print(
                f"ERROR: expected no docs older than {cutoff.isoformat()} after cleanup, "
                f"found {remaining_old}",
                file=sys.stderr,
            )
            return 3
    elif len(final_docs) > args.keep:
        print(
            f"ERROR: expected at most {args.keep} docs after cleanup, found {len(final_docs)}",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
