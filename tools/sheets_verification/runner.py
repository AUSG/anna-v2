"""Opt-in integration probe using the actual store and new tabs in a test document.

This does not start Anna, Slack handlers, or scheduled jobs. Credentials and cell
values stay in memory. Reports contain hashes, synthetic user IDs, and outcomes.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from gspread.exceptions import APIError
from requests import Response
from requests.exceptions import ConnectionError

from features.bigchat.errors import BigchatNameConflict, BigchatSheetMissing
from integrations.bigchat_store import BigchatStore
from integrations.google_sheets import GoogleSpreadsheetClient
from tools.sheets_verification.boundary import SheetsTestBoundary, attach_boundary

SOURCE_PATHS = (
    "src",
    "tools/__init__.py",
    "tools/sheets_verification",
    "pyproject.toml",
    "uv.lock",
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def unsortable_rows_reason(rows):
    """Why sorting these rows by column A might leave them in place, or None.

    The sort cases and the values-only control must move participants. Ties in
    column A, or rows already in order, would fail a correct store only after
    every test tab was written, so they are rejected before any write.
    """
    keys = [row[0] for row in rows]
    if len({key.casefold() for key in keys}) != len(keys):
        return "Column A values must differ, ignoring case, so every sort moves rows"
    if keys == sorted(keys) or keys == sorted(keys, key=str.casefold):
        return "Source rows are already sorted by column A; shuffle them first"
    return None


def source_manifest(expected_head):
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if head != expected_head:
        raise RuntimeError("The checkout does not match --expected-head")
    subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *SOURCE_PATHS],
        cwd=ROOT,
        check=True,
    )
    if subprocess.check_output(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *SOURCE_PATHS,
        ],
        cwd=ROOT,
    ):
        raise RuntimeError(
            "Untracked application or verification files are not allowed"
        )
    files = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--", *SOURCE_PATHS],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    return {
        "head": head,
        "python": sys.version,
        "files": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in files
            if name and (ROOT / name).is_file()
        },
    }


class LiveProbe:
    def __init__(self, options, credentials):
        if not options.run:
            raise RuntimeError("Explicit --run is required")
        self.options = options
        self.source = source_manifest(options.expected_head)
        if (
            credentials.get("type") != "service_account"
            or credentials.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise RuntimeError("Use a Google service-account JSON credential")
        self.out = Path(options.output).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.run_id = uuid4().hex
        self.prefix = "ANNA_TEST_" + self.run_id[:8] + "_"
        self.policy = SheetsTestBoundary(
            options.spreadsheet_id, options.source_sheet_id, self.prefix
        )
        fields = [
            "type",
            "project_id",
            "private_key_id",
            "private_key",
            "client_email",
            "client_id",
            "auth_uri",
            "token_uri",
            "auth_provider_x509_cert_url",
            "client_x509_cert_url",
        ]
        settings = SimpleNamespace(
            **{"GCP_" + key: credentials[key] for key in fields},
            FORM_SPREADSHEET_ID=options.spreadsheet_id,
            MEMBERS_INFO_WORKSHEET_ID=options.source_sheet_id,
        )
        self.client = GoogleSpreadsheetClient(settings)
        self.store = BigchatStore(self.client)
        self.audit = []
        self.stage = "preflight"
        self.lose_write = None
        self.fail_read = False
        attach_boundary(
            self.client.gs_client.http_client.session, self.policy, self.record
        )
        self.results: list[dict] = []
        self.report: dict = {
            "run_id": self.run_id,
            "source": self.source,
            "test_document": options.spreadsheet_id,
            "source_copy_gid": options.source_sheet_id,
            "started_at": datetime.now(UTC).isoformat(),
            "complete": False,
            "results": self.results,
        }

    def save(self, name, data):
        (self.out / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )

    def record(self, method, url, body, kind, status):
        entry = {
            "stage": self.stage,
            "method": method,
            "url": url,
            "kind": kind,
            "status": status,
            "body_sha256": fingerprint(body),
        }
        lose_write = (
            kind == "write" and self.lose_write and url.endswith(self.lose_write)
        )
        if lose_write:
            entry["injected_failure_after_response"] = "connection_lost"
        fail_read = kind == "read" and self.fail_read
        if fail_read:
            entry["injected_failure_after_response"] = "503"
        self.audit.append(entry)
        self.save("request-audit.json", self.audit)
        if lose_write:
            self.lose_write = None
            raise ConnectionError("Test-only lost response after committed write")
        if fail_read:
            self.fail_read = False
            response = Response()
            response.status_code = 503
            response._content = (
                b'{"error":{"code":503,"message":"test-only transient read failure"}}'
            )
            raise APIError(response)

    def request(self, method, suffix, body=None):
        return self.client.sheets_request(method, suffix, body)

    def document(self):
        return self.request("get", "")

    def metadata(self):
        response = self.request(
            "post",
            "/developerMetadata:search",
            {"dataFilters": [{"developerMetadataLookup": {"visibility": "DOCUMENT"}}]},
        )
        return {
            match["developerMetadata"]["metadataId"]: match["developerMetadata"]
            for match in response.get("matchedDeveloperMetadata", [])
        }

    def values(self, sid):
        response = self.request(
            "post",
            "/values:batchGetByDataFilter",
            {
                "dataFilters": [{"gridRange": {"sheetId": sid}}],
                "valueRenderOption": "UNFORMATTED_VALUE",
            },
        )
        ranges = response.get("valueRanges", [])
        if len(ranges) != 1:
            raise RuntimeError("Fixture values were not uniquely selected")
        return ranges[0]["valueRange"].get("values", [])

    def batch(self, requests):
        return self.request("post", ":batchUpdate", {"requests": requests})

    def plan(self, label, count, role="clone"):
        channel, thread = "C_ANNA_TEST", f"{self.run_id}.{label}"
        event = self.store.event_identity(channel, thread)
        sheet = self.store.sheet_identity(channel, thread)
        sid, title = sheet.metadata_id, self.prefix + label
        self.policy.add_sheet(sid, title, role)
        self.policy.add_metadata(event.to_api(), sid, "document")
        self.policy.add_metadata(sheet.to_api(), sid, "sheet")
        users = [f"U_TEST_{i + 1:03d}" for i in range(count)]
        participants = [self.store._participant(event, user) for user in users]
        for identity in participants:
            self.policy.add_metadata(identity.to_api(), sid, "row")
        return {
            "label": label,
            "sheet_id": sid,
            "title": title,
            "event": event,
            "sheet": sheet,
            "users": users,
            "participants": participants,
            "kwargs": {"channel": channel, "thread_ts": thread},
        }

    def seed_copy(self, plan):
        sid = plan["sheet_id"]
        requests = [
            {
                "duplicateSheet": {
                    "sourceSheetId": self.options.source_sheet_id,
                    "newSheetId": sid,
                    "newSheetName": plan["title"],
                }
            }
        ]
        requests.extend(
            {
                "createDeveloperMetadata": {
                    "developerMetadata": {
                        **identity.to_api(),
                        "visibility": "DOCUMENT",
                        "location": location,
                    }
                }
            }
            for identity, location in [
                (plan["event"], {"spreadsheet": True}),
                (plan["sheet"], {"sheetId": sid}),
            ]
        )
        for i, identity in enumerate(plan["participants"]):
            requests.append(
                {
                    "createDeveloperMetadata": {
                        "developerMetadata": {
                            **identity.to_api(),
                            "visibility": "DOCUMENT",
                            "location": {
                                "dimensionRange": {
                                    "sheetId": sid,
                                    "dimension": "ROWS",
                                    "startIndex": i,
                                    "endIndex": i + 1,
                                }
                            },
                        }
                    }
                }
            )
        self.batch(requests)

    def snapshot(self, plan, expected):
        metadata, raw = self.metadata(), self.values(plan["sheet_id"])
        rows = [([str(v) for v in row] + [""] * 4)[:4] for row in raw]
        bindings = []
        for i, identity in enumerate(plan["participants"]):
            entry = metadata.get(identity.metadata_id, {})
            area = entry.get("location", {}).get("dimensionRange", {})
            index = area.get("startIndex", -1)
            value = rows[index] if 0 <= index < len(rows) else [""] * 4
            valid = (
                all(entry.get(k) == v for k, v in identity.to_api().items())
                and area.get("sheetId") == plan["sheet_id"]
                and area.get("dimension") == "ROWS"
                and area.get("endIndex") == index + 1
            )
            bindings.append(
                {
                    "user": plan["users"][i],
                    "row": index,
                    "matches": valid and value == expected[i],
                    "value_sha256": fingerprint(value),
                }
            )
        return {
            "bindings": bindings,
            "matches": sum(b["matches"] for b in bindings),
            "row_fingerprints": [fingerprint(row) for row in rows if any(row)],
            "cells_sha256": fingerprint(raw),
        }

    def result(self, result):
        self.results.append(result)
        self.save("results.json", self.report)
        print(
            "RESULT "
            + json.dumps({k: v for k, v in result.items() if k != "snapshots"}),
            flush=True,
        )

    def exercise(self, plan, expected, before, *, negative=False, sorted_case=False):
        sid, kw = plan["sheet_id"], plan["kwargs"]
        current = self.snapshot(plan, expected)
        moved = [
            i
            for i, b in enumerate(current["bindings"])
            if b["row"] != before["bindings"][i]["row"]
        ]
        mismatches = [i for i, b in enumerate(current["bindings"]) if not b["matches"]]
        target = (mismatches or moved or [1])[0]
        uid = plan["users"][target]
        if plan["label"] == "control":
            self.lose_write = "/values:batchUpdateByDataFilter"
        cancelled = self.store.cancel(sid, uid, **kw)
        after_expected = copy_rows(expected)
        after_expected[target] = [""] * 4
        after_cancel = self.snapshot(plan, after_expected)
        only_target = after_cancel["matches"] == len(expected) and Counter(
            after_cancel["row_fingerprints"]
        ) == Counter(fingerprint(row) for i, row in enumerate(expected) if i != target)
        self.lose_write = ":batchUpdate" if plan["label"] == "control" else None
        rejoined = self.store.register(sid, uid, expected[target], **kw)
        after_rejoin = self.snapshot(plan, expected)
        restored = after_rejoin["matches"] == len(expected) and Counter(
            after_rejoin["row_fingerprints"]
        ) == Counter(fingerprint(row) for row in expected)
        at_end = after_rejoin["row_fingerprints"][-1] == fingerprint(expected[target])
        writes = sum(e["kind"] == "write" for e in self.audit)
        duplicate = self.store.register(sid, uid, expected[target], **kw)
        no_duplicate_write = writes == sum(e["kind"] == "write" for e in self.audit)
        sort_observed = (
            bool(moved) and current["cells_sha256"] != before["cells_sha256"]
        )
        passed = (
            (current["matches"] < len(expected) and not only_target and not restored)
            if negative
            else (
                current["matches"] == len(expected)
                and cancelled
                and only_target
                and rejoined
                and restored
                and at_end
                and not duplicate
                and no_duplicate_write
                and (not sorted_case or sort_observed)
            )
        )
        self.result(
            {
                "label": plan["label"],
                "passed": passed,
                "expected_negative_control": negative,
                "sheet_id": sid,
                "participants": len(expected),
                "binding_matches": current["matches"],
                "moved_rows": len(moved),
                "cancel_only_target": only_target,
                "reregister_restored_all": restored,
                "reregister_at_end": at_end,
                "duplicate_register_wrote_nothing": no_duplicate_write,
                "snapshots": {
                    "before": before,
                    "sorted": current,
                    "cancelled": after_cancel,
                    "reregistered": after_rejoin,
                },
            }
        )

    def run(self):
        doc = self.document()
        original_meta = self.metadata()
        source = next(
            s
            for s in doc["sheets"]
            if s["properties"]["sheetId"] == self.options.source_sheet_id
        )
        grid = source["properties"]["gridProperties"]
        if grid["rowCount"] > 2000 or grid["columnCount"] > 50:
            raise RuntimeError("Use a small, dedicated test copy")
        original = self.values(self.options.source_sheet_id)
        if not 3 <= len(original) <= 100 or any(len(row) != 4 for row in original):
            raise RuntimeError(
                "The source copy must contain 3-100 distinct four-column participant rows"
            )
        rows = [[str(v) for v in row] for row in original]
        if len({tuple(row) for row in rows}) != len(rows):
            raise RuntimeError("Source rows must be unique for independent comparison")
        reason = unsortable_rows_reason(rows)
        if reason:
            raise RuntimeError(reason)
        labels = ["control", "sheet", "range", "filter", "values"]
        if self.options.browser:
            labels += ["ui_sheet", "ui_range", "ui_filter"]
        plans = [self.plan(label, len(rows)) for label in labels]
        fresh, deleted, full = (
            self.plan("create", 3, "create"),
            self.plan("deleted", 1, "delete"),
            self.plan("full", 2, "full"),
        )
        conflict = self.plan("duplicate", 0, "create")
        self.policy.arm(
            [s["properties"]["sheetId"] for s in doc["sheets"]], original_meta
        )
        self.report["source_copy_sha256"] = fingerprint(original)
        self.report["planned_tabs"] = [
            {"label": p["label"], "sheet_id": p["sheet_id"], "title": p["title"]}
            for p in [fresh, deleted, full, conflict, *plans]
        ]
        self.save("results.json", self.report)

        self.stage = "create-and-order"
        created = self.store.create(fresh["title"], **fresh["kwargs"])
        repeated = self.store.create(fresh["title"], **fresh["kwargs"])
        props = next(
            s["properties"]
            for s in self.document()["sheets"]
            if s["properties"]["sheetId"] == created.worksheet_id
        )
        fake = [
            [name, "test", name.lower() + "@example.invalid", "000"]
            for name in ["Charlie", "Alpha", "Bravo"]
        ]
        self.lose_write = ":batchUpdate"
        for uid, values in zip(fresh["users"], fake, strict=True):
            assert self.store.register(
                created.worksheet_id, uid, values, **fresh["kwargs"]
            )
        ordered = self.values(created.worksheet_id)
        self.result(
            {
                "label": "creation_and_ASC",
                "passed": created == repeated
                and props["index"] == min(3, len(doc["sheets"]))
                and ordered == fake,
                "tab_index": props["index"],
                "lost_response_reconciled": self.lose_write is None,
            }
        )
        # Reminder recipients depend on how the real API answers a participant
        # search and echoes data filters; the in-memory double cannot show that.
        recipients = self.store.active_user_ids(created.worksheet_id)
        self.result(
            {
                "label": "reminder_recipients",
                "passed": sorted(recipients) == sorted(fresh["users"]),
            }
        )
        before = self.snapshot(fresh, fake)
        self.exercise(fresh, fake, before)
        if self.options.read_retry:
            self.fail_read = True
            self.result(
                {
                    "label": "transient_read_recovery",
                    "passed": self.store.find(**fresh["kwargs"]) == created.worksheet_id
                    and not self.fail_read,
                }
            )
        self.stage = "duplicate-title"
        writes = sum(e["kind"] == "write" for e in self.audit)
        try:
            self.store.create(fresh["title"], **conflict["kwargs"])
        except BigchatNameConflict:
            self.result(
                {
                    "label": "duplicate_title",
                    "passed": writes == sum(e["kind"] == "write" for e in self.audit)
                    and self.store.find(**conflict["kwargs"]) is None,
                }
            )
        else:
            raise AssertionError("Duplicate title was accepted")

        self.stage = "deleted-tab"
        gone = self.store.create(deleted["title"], **deleted["kwargs"])
        self.store.register(
            gone.worksheet_id, deleted["users"][0], fake[0], **deleted["kwargs"]
        )
        self.batch([{"deleteSheet": {"sheetId": gone.worksheet_id}}])
        writes = sum(e["kind"] == "write" for e in self.audit)
        missing = []
        for label, operation in [
            ("find", lambda: self.store.find(**deleted["kwargs"])),
            (
                "create",
                lambda: self.store.create(deleted["title"], **deleted["kwargs"]),
            ),
            (
                "register",
                lambda: self.store.register(
                    gone.worksheet_id, deleted["users"][0], fake[0], **deleted["kwargs"]
                ),
            ),
            (
                "cancel",
                lambda: self.store.cancel(
                    gone.worksheet_id, deleted["users"][0], **deleted["kwargs"]
                ),
            ),
        ]:
            try:
                operation()
            except BigchatSheetMissing:
                missing.append(label)
        self.result(
            {
                "label": "deleted_tab",
                "passed": len(missing) == 4
                and writes == sum(e["kind"] == "write" for e in self.audit),
                "missing_notices": missing,
            }
        )

        self.stage = "full-grid"
        filled = self.store.create(full["title"], **full["kwargs"])
        self.store.register(
            filled.worksheet_id, full["users"][0], fake[0], **full["kwargs"]
        )
        self.batch(
            [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": filled.worksheet_id,
                            "gridProperties": {"rowCount": 1},
                        },
                        "fields": "gridProperties.rowCount",
                    }
                }
            ]
        )
        self.store.register(
            filled.worksheet_id, full["users"][1], fake[1], **full["kwargs"]
        )
        self.result(
            {
                "label": "full_grid",
                "passed": self.values(filled.worksheet_id) == fake[:2],
            }
        )

        for plan in plans:
            self.stage = plan["label"]
            self.seed_copy(plan)
            before = self.snapshot(plan, rows)
            assert before["matches"] == len(rows)
            label, sid = plan["label"], plan["sheet_id"]
            if label.startswith("ui_"):
                print(
                    "READY_UI "
                    + json.dumps(
                        {
                            "label": label,
                            "url": self.client.get_url(sid),
                            "title": plan["title"],
                            "range": f"A1:D{len(rows)}",
                        }
                    ),
                    flush=True,
                )
                if input().strip() != label:
                    raise RuntimeError(
                        "UI acknowledgement did not match the requested test tab"
                    )
            elif label in {"sheet", "range", "filter"}:
                area = {
                    "sheetId": sid,
                    "startRowIndex": 0,
                    "endRowIndex": grid["rowCount"] if label == "sheet" else len(rows),
                    "startColumnIndex": 0,
                    "endColumnIndex": grid["columnCount"] if label == "sheet" else 4,
                }
                spec = {
                    "range": area,
                    "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}],
                }
                self.batch(
                    [{"setBasicFilter": {"filter": spec}}]
                    if label == "filter"
                    else [{"sortRange": spec}]
                )
            elif label == "values":
                area = "'" + plan["title"] + f"'!A1:D{len(rows)}"
                self.policy.value_overwrites[area] = len(rows)
                self.request(
                    "put",
                    "/values/" + quote(area, safe="") + "?valueInputOption=RAW",
                    {
                        "majorDimension": "ROWS",
                        "values": sorted(rows, key=lambda row: row[0]),
                    },
                )
            self.exercise(
                plan,
                rows,
                before,
                negative=label == "values",
                sorted_case=label not in {"control", "values"},
            )

        self.stage = "final-readback"
        source_after = self.values(self.options.source_sheet_id)
        final_source = source_manifest(self.options.expected_head)
        final_metadata = self.metadata()
        unchanged_metadata = all(
            final_metadata.get(mid) == metadata
            for mid, metadata in original_meta.items()
        )
        self.report.update(
            complete=True,
            all_expected_checks_passed=all(r["passed"] for r in self.results),
            source_copy_unchanged=source_after == original,
            original_metadata_unchanged=unchanged_metadata,
            exact_source_unchanged=final_source["files"] == self.source["files"],
            writes=sum(e["kind"] == "write" for e in self.audit),
            requests=len(self.audit),
            browser_checked=self.options.browser,
            finished_at=datetime.now(UTC).isoformat(),
        )
        self.save("results.json", self.report)
        if not all(
            self.report[k]
            for k in [
                "all_expected_checks_passed",
                "source_copy_unchanged",
                "original_metadata_unchanged",
                "exact_source_unchanged",
            ]
        ):
            raise AssertionError(
                "A live verification check failed; inspect results.json"
            )
        print(
            "COMPLETE "
            + json.dumps(
                {
                    k: v
                    for k, v in self.report.items()
                    if k not in {"source", "planned_tabs", "results"}
                }
            ),
            flush=True,
        )


def copy_rows(rows):
    return [list(row) for row in rows]


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--source-sheet-id", type=int, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--read-retry", action="store_true")
    return parser.parse_args()


def main():
    options = arguments()
    LiveProbe(options, json.loads(options.credentials.read_text())).run()
