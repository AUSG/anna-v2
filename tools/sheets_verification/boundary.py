"""Fail-closed transport policy owned by the opt-in Sheets verification tool."""

import hashlib
import json
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit


class BoundaryError(RuntimeError):
    pass


class SheetsTestBoundary:
    def __init__(self, document_id, source_sheet_id, prefix):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", document_id):
            raise BoundaryError("Invalid test document ID")
        self.base = f"https://sheets.googleapis.com/v4/spreadsheets/{document_id}"
        self.source_sheet_id = source_sheet_id
        self.prefix = prefix
        self.sheets = {}
        self.metadata = {}
        self.existing_metadata = set()
        self.value_overwrites = {}
        self.armed = False

    def add_sheet(self, sheet_id, title, role):
        if (
            type(sheet_id) is not int
            or sheet_id <= 0
            or sheet_id == self.source_sheet_id
            or sheet_id in self.sheets
        ):
            raise BoundaryError("Invalid or repeated test worksheet ID")
        if not title.startswith(self.prefix) or role not in {
            "clone",
            "create",
            "delete",
            "full",
        }:
            raise BoundaryError("Unplanned worksheet role or name")
        self.sheets[sheet_id] = (title, role)

    def add_metadata(self, fields, sheet_id, location):
        self._owned(sheet_id)
        self._keys(fields, {"metadataId", "metadataKey", "metadataValue"})
        mid = fields.get("metadataId")
        if (
            type(mid) is not int
            or mid <= 0
            or mid in self.metadata
            or location not in {"document", "sheet", "row"}
        ):
            raise BoundaryError("Invalid or repeated test metadata ID")
        self.metadata[mid] = (dict(fields), sheet_id, location)

    def arm(self, existing_sheets, existing_metadata):
        if set(self.sheets) & set(existing_sheets) or set(self.metadata) & set(
            existing_metadata
        ):
            raise BoundaryError("Test identities must be new")
        self.existing_metadata = set(existing_metadata)
        self.armed = True

    def _owned(self, sheet_id):
        if type(sheet_id) is not int or sheet_id not in self.sheets:
            raise BoundaryError("Write is outside newly planned test tabs")
        return self.sheets[sheet_id]

    @staticmethod
    def _keys(obj, allowed):
        if not isinstance(obj, dict) or set(obj) - allowed:
            raise BoundaryError("Unexpected request fields")

    def _grid(self, area):
        self._keys(
            area,
            {
                "sheetId",
                "startRowIndex",
                "endRowIndex",
                "startColumnIndex",
                "endColumnIndex",
            },
        )
        self._owned(area.get("sheetId"))
        for key, value in area.items():
            if key != "sheetId" and (type(value) is not int or not 0 <= value <= 2000):
                raise BoundaryError("Invalid test grid range")

    @staticmethod
    def _revision_fields(fields, value):
        """Validate a revision independently of the production schema helpers."""
        if value == fields["metadataValue"]:
            return fields
        try:
            parts = json.loads(value)
            owner = json.loads(fields["metadataValue"])
        except (TypeError, ValueError) as error:
            raise BoundaryError("Invalid participant revision") from error
        if (
            fields["metadataKey"] != "anna.participant.v1"
            or not isinstance(parts, list)
            or len(parts) != 5
            or parts[:2] != owner
            or not isinstance(parts[2], str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+", parts[2])
            or type(parts[3]) is not bool
            or not isinstance(parts[4], str)
            or not re.fullmatch(r"[0-9a-f]{32}", parts[4])
        ):
            raise BoundaryError("Revision must retain the approved participant owner")
        return {**fields, "metadataValue": value}

    def _lookup(self, lookup, *, row_only=True):
        self._keys(
            lookup,
            {
                "metadataId",
                "metadataKey",
                "metadataValue",
                "visibility",
                "locationType",
                "metadataLocation",
                "locationMatchingStrategy",
            },
        )
        expected = self.metadata.get(lookup.get("metadataId"))
        if not expected:
            raise BoundaryError("Unknown metadata write target")
        fields, sid, kind = expected
        fields = self._revision_fields(fields, lookup.get("metadataValue"))
        if kind != "row" or lookup != {
            **fields,
            "visibility": "DOCUMENT",
            **({"locationType": "ROW"} if row_only else {}),
            "metadataLocation": {"sheetId": sid},
            "locationMatchingStrategy": "INTERSECTING_LOCATION",
        }:
            raise BoundaryError(
                "Metadata write is not restricted to one owned participant"
            )
        return expected

    def _create_metadata(self, meta):
        self._keys(
            meta,
            {"metadataId", "metadataKey", "metadataValue", "visibility", "location"},
        )
        mid = meta.get("metadataId")
        if (
            mid not in self.metadata
            and meta.get("metadataKey") == "anna.registration.v1"
        ):
            # Rejoining uses a fresh random replay guard. It must refer to an
            # already authorized participant and be on that participant's tab.
            parts = json.loads(meta.get("metadataValue", "null"))
            if (
                not isinstance(parts, list)
                or len(parts) != 2
                or not all(isinstance(p, str) for p in parts)
                or not parts[0].isdigit()
                or not re.fullmatch(r"[0-9a-f]{32}", parts[1])
            ):
                raise BoundaryError("Unexpected registration guard")
            participant = self.metadata.get(int(parts[0]))
            if (
                not participant
                or participant[2] != "row"
                or participant[0]["metadataKey"] != "anna.participant.v1"
                or mid in self.existing_metadata
            ):
                raise BoundaryError("Registration guard has an unapproved participant")
            value = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
            expected_id = (
                int.from_bytes(
                    hashlib.sha256(f"anna.registration.v1:{value}".encode()).digest()[
                        :4
                    ],
                    "big",
                )
                & 0x7FFFFFFF
                or 1
            )
            if mid != expected_id:
                raise BoundaryError("Registration guard identity mismatch")
            self.add_metadata(
                {k: meta[k] for k in ("metadataId", "metadataKey", "metadataValue")},
                participant[1],
                "row",
            )
        expected = self.metadata.get(mid)
        if not expected:
            raise BoundaryError("Unplanned metadata creation")
        fields, sid, kind = expected
        fields = self._revision_fields(fields, meta.get("metadataValue"))
        if meta.get("visibility") != "DOCUMENT" or any(
            meta.get(k) != v for k, v in fields.items()
        ):
            raise BoundaryError("Metadata identity mismatch")
        location = meta.get("location", {})
        if kind == "document":
            if location != {"spreadsheet": True}:
                raise BoundaryError("Unexpected document record location")
        elif kind == "sheet":
            if location != {"sheetId": sid}:
                raise BoundaryError("Unexpected sheet binding location")
        else:
            if (
                location == {"sheetId": sid}
                and fields["metadataKey"] == "anna.participant.v1"
            ):
                parts = json.loads(fields["metadataValue"])
                if len(parts) == 5 and parts[3] is False:
                    return
                raise BoundaryError("Only a versioned cancellation may be sheet-scoped")
            self._keys(location, {"dimensionRange"})
            area = location.get("dimensionRange", {})
            start = area.get("startIndex")
            if (
                type(start) is not int
                or not 0 <= start < 2000
                or area
                != {
                    "sheetId": sid,
                    "dimension": "ROWS",
                    "startIndex": start,
                    "endIndex": start + 1,
                }
            ):
                raise BoundaryError("Metadata must belong to one owned row")

    def _batch_item(self, item):
        if not isinstance(item, dict) or len(item) != 1:
            raise BoundaryError("Malformed batch item")
        kind, body = next(iter(item.items()))
        if kind == "duplicateSheet":
            self._keys(body, {"sourceSheetId", "newSheetId", "newSheetName"})
            title, role = self._owned(body.get("newSheetId"))
            if (
                body
                != {
                    "sourceSheetId": self.source_sheet_id,
                    "newSheetId": body["newSheetId"],
                    "newSheetName": title,
                }
                or role != "clone"
            ):
                raise BoundaryError("Only the preserved test copy may be duplicated")
        elif kind == "addSheet":
            self._keys(body, {"properties"})
            props = body.get("properties", {})
            self._keys(props, {"sheetId", "title", "index", "gridProperties"})
            title, role = self._owned(props.get("sheetId"))
            if (
                role == "clone"
                or props.get("title") != title
                or props.get("gridProperties") != {"rowCount": 100, "columnCount": 4}
                or type(props.get("index")) is not int
                or not 0 <= props["index"] <= 3
            ):
                raise BoundaryError("Unexpected test tab creation")
        elif kind == "createDeveloperMetadata":
            self._keys(body, {"developerMetadata"})
            self._create_metadata(body["developerMetadata"])
        elif kind == "deleteDeveloperMetadata":
            self._keys(body, {"dataFilter"})
            self._keys(body["dataFilter"], {"developerMetadataLookup"})
            self._lookup(body["dataFilter"]["developerMetadataLookup"], row_only=False)
        elif kind == "updateDeveloperMetadata":
            self._keys(body, {"dataFilters", "developerMetadata", "fields"})
            filters = body.get("dataFilters", [])
            if len(filters) != 1 or body.get("fields") != "metadataValue":
                raise BoundaryError("Only one participant revision may be updated")
            self._keys(filters[0], {"developerMetadataLookup"})
            fields, _, _ = self._lookup(
                filters[0].get("developerMetadataLookup", {}), row_only=False
            )
            updated = body.get("developerMetadata", {})
            self._keys(updated, {"metadataValue"})
            self._revision_fields(fields, updated.get("metadataValue"))
        elif kind == "insertDimension":
            self._keys(body, {"range", "inheritFromBefore"})
            area = body.get("range", {})
            self._owned(area.get("sheetId"))
            start = area.get("startIndex")
            if (
                type(start) is not int
                or not 0 <= start < 2000
                or area
                != {
                    "sheetId": area["sheetId"],
                    "dimension": "ROWS",
                    "startIndex": start,
                    "endIndex": start + 1,
                }
                or body.get("inheritFromBefore") is not False
            ):
                raise BoundaryError("Unexpected test row insertion")
        elif kind == "appendDimension":
            self._owned(body.get("sheetId"))
            if body != {"sheetId": body["sheetId"], "dimension": "ROWS", "length": 1}:
                raise BoundaryError("Unexpected test grid extension")
        elif kind == "updateCells":
            self._keys(body, {"start", "rows", "fields"})
            start = body.get("start", {})
            self._owned(start.get("sheetId"))
            self._keys(start, {"sheetId", "rowIndex", "columnIndex"})
            if (
                type(start.get("rowIndex")) is not int
                or not 0 <= start["rowIndex"] < 2000
                or start.get("columnIndex") != 0
                or body.get("fields") != "userEnteredValue"
            ):
                raise BoundaryError("Cell write is outside participant columns")
            rows = body.get("rows", [])
            if (
                len(rows) != 1
                or set(rows[0]) != {"values"}
                or len(rows[0]["values"]) != 4
            ):
                raise BoundaryError("Cell write must be one participant")
            for cell in rows[0]["values"]:
                if (
                    set(cell) != {"userEnteredValue"}
                    or set(cell["userEnteredValue"]) != {"stringValue"}
                    or not isinstance(cell["userEnteredValue"]["stringValue"], str)
                ):
                    raise BoundaryError("Only literal participant values are permitted")
        elif kind == "updateDimensionProperties":
            sid = body.get("range", {}).get("sheetId")
            self._owned(sid)
            if body != {
                "range": {
                    "sheetId": sid,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 4,
                },
                "properties": {"pixelSize": 220},
                "fields": "pixelSize",
            }:
                raise BoundaryError("Unexpected column formatting")
        elif kind in {"sortRange", "setBasicFilter"}:
            if kind == "setBasicFilter":
                self._keys(body, {"filter"})
                body = body["filter"]
            self._keys(body, {"range", "sortSpecs"})
            self._grid(body.get("range", {}))
            if body.get("sortSpecs") != [
                {"dimensionIndex": 0, "sortOrder": "ASCENDING"}
            ]:
                raise BoundaryError("Unexpected test sort")
        elif kind == "deleteSheet":
            self._keys(body, {"sheetId"})
            if self._owned(body.get("sheetId"))[1] != "delete":
                raise BoundaryError("Only a new deletion-test tab may be deleted")
        elif kind == "updateSheetProperties":
            sid = body.get("properties", {}).get("sheetId")
            if self._owned(sid)[1] != "full" or body != {
                "properties": {"sheetId": sid, "gridProperties": {"rowCount": 1}},
                "fields": "gridProperties.rowCount",
            }:
                raise BoundaryError("Only the new full-grid fixture may be resized")
        else:
            raise BoundaryError("Operation is not needed for this verification")

    def check(self, method, url, body=None):
        parsed = urlsplit(url)
        path = unquote(parsed.path)
        root = urlsplit(self.base).path
        if (
            parsed.scheme != "https"
            or parsed.netloc != "sheets.googleapis.com"
            or parsed.fragment
            or not path.startswith(root)
        ):
            raise BoundaryError("Only the explicit test document is allowed")
        suffix = path[len(root) :]
        method = method.upper()
        if method == "GET" and (
            suffix == ""
            or re.fullmatch(r"/developerMetadata/[1-9][0-9]*", suffix)
            or suffix.startswith("/values/")
        ):
            return "read"
        if method == "POST" and suffix in {
            "/developerMetadata:search",
            "/values:batchGetByDataFilter",
        }:
            return "read"
        if not self.armed:
            raise BoundaryError("Writes require a successful identity preflight")
        if not isinstance(body, dict):
            raise BoundaryError("Writes require a JSON object")
        if method == "POST" and suffix == ":batchUpdate":
            self._keys(body, {"requests"})
            if (
                not isinstance(body.get("requests"), list)
                or not 1 <= len(body["requests"]) <= 200
            ):
                raise BoundaryError("Unexpected batch size")
            for item in body["requests"]:
                self._batch_item(item)
            return "write"
        if method == "POST" and suffix == "/values:batchUpdateByDataFilter":
            self._keys(body, {"valueInputOption", "data"})
            if body.get("valueInputOption") != "RAW" or len(body.get("data", [])) != 1:
                raise BoundaryError("Unexpected filtered values update")
            entry = body["data"][0]
            self._keys(entry, {"dataFilter", "majorDimension", "values"})
            if (
                set(entry.get("dataFilter", {})) != {"developerMetadataLookup"}
                or entry.get("majorDimension") != "ROWS"
            ):
                raise BoundaryError("A participant metadata filter is required")
            self._lookup(entry["dataFilter"]["developerMetadataLookup"])
            if (
                len(entry.get("values", [])) != 1
                or len(entry["values"][0]) != 4
                or not all(isinstance(v, str) for v in entry["values"][0])
            ):
                raise BoundaryError("Only one A:D row may be updated")
            return "write"
        if method == "PUT" and suffix.startswith("/values/"):
            area = suffix[len("/values/") :]
            rows = body.get("values", [])
            self._keys(body, {"majorDimension", "values"})
            if (
                area not in self.value_overwrites
                or len(rows) != self.value_overwrites[area]
                or parse_qs(parsed.query).get("valueInputOption") != ["RAW"]
                or body.get("majorDimension") != "ROWS"
                or any(
                    len(row) != 4 or not all(isinstance(v, str) for v in row)
                    for row in rows
                )
            ):
                raise BoundaryError(
                    "Only the designated negative control may overwrite values"
                )
            return "write"
        raise BoundaryError("Endpoint or method is not permitted")


def attach_boundary(session, policy, record, interval=1.1):
    original = session.send
    last = {"read": 0.0, "write": 0.0}

    def guarded(request, **kwargs):
        raw = request.body
        body = json.loads(raw) if raw else None
        kind = policy.check(request.method, request.url, body)
        remaining = interval - (time.monotonic() - last[kind])
        if remaining > 0:
            time.sleep(remaining)
        last[kind] = time.monotonic()
        kwargs["allow_redirects"] = False
        try:
            response = original(request, **kwargs)
        except BaseException:
            record(request.method, request.url, body, kind, None)
            raise
        record(request.method, request.url, body, kind, response.status_code)
        if 300 <= response.status_code < 400:
            raise BoundaryError("Redirects are forbidden")
        return response

    session.send = guarded
