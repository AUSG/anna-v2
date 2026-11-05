"""Small Sheets API oracle: atomic batches, unique metadata IDs and moving rows.

This models the HTTP contract, not BigchatStore's algorithm or identity hashing.
No Google credentials or external connections are used.
"""

import copy
import json
import threading

from gspread.exceptions import APIError
from requests import Response
from requests.exceptions import ConnectionError


def api_error(status):
    response = Response()
    response.status_code = status
    response._content = json.dumps(
        {"error": {"code": status, "message": "simulated API error"}}
    ).encode()
    return APIError(response)


class SheetsAPI:
    def __init__(self):
        self.members_worksheet_id = 42
        self.spreadsheet_id = "configured-document"
        self.sheets = {}
        self.sheet_order = []
        self.metadata = {}
        self.calls = []
        self.fail_after = None
        self.before_write = None
        self.lock = threading.RLock()

    def get_worksheet_title(self, worksheet_id):
        return self.sheets[worksheet_id]["title"]

    def get_values(self, worksheet_id):
        return copy.deepcopy(self.sheets[worksheet_id]["rows"])

    def get_url(self, worksheet_id):
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={worksheet_id}"

    def add_legacy_sheet(self, worksheet_id, rows, title=None):
        self.sheets[worksheet_id] = {
            "title": title or f"Legacy bigchat {worksheet_id}",
            "rows": copy.deepcopy(rows),
            "gridProperties": {"rowCount": max(100, len(rows)), "columnCount": 30},
        }
        self.sheet_order.append(worksheet_id)

    def delete_sheet(self, worksheet_id):
        del self.sheets[worksheet_id]
        self.sheet_order.remove(worksheet_id)
        for mid, metadata in list(self.metadata.items()):
            location = metadata["location"]
            if (
                location.get("sheetId") == worksheet_id
                or location.get("dimensionRange", {}).get("sheetId") == worksheet_id
            ):
                del self.metadata[mid]

    def sort_rows(self, worksheet_id, *, values_only=False):
        rows = self.sheets[worksheet_id]["rows"]
        order = sorted(range(len(rows)), key=lambda i: rows[i][0] if rows[i] else "")
        self.sheets[worksheet_id]["rows"] = [rows[i] for i in order]
        if not values_only:
            for metadata in self.metadata.values():
                location = metadata["location"].get("dimensionRange", {})
                if location.get("sheetId") == worksheet_id:
                    index = order.index(location["startIndex"])
                    location.update(startIndex=index, endIndex=index + 1)

    def insert_row(self, worksheet_id, index, values):
        sheet = self.sheets[worksheet_id]
        if not 0 <= index < sheet["gridProperties"]["rowCount"]:
            raise api_error(400)
        while len(sheet["rows"]) < index:
            sheet["rows"].append([])
        sheet["rows"].insert(index, list(values))
        sheet["gridProperties"]["rowCount"] += 1
        for metadata in self.metadata.values():
            location = metadata["location"].get("dimensionRange", {})
            if (
                location.get("sheetId") == worksheet_id
                and location["startIndex"] >= index
            ):
                location["startIndex"] += 1
                location["endIndex"] += 1

    def _matched_metadata(self, data_filter):
        query = data_filter["developerMetadataLookup"]
        matches = []
        for mid, metadata in self.metadata.items():
            if any(
                metadata.get(k) != query[k]
                for k in ("metadataId", "metadataKey", "metadataValue", "visibility")
                if k in query
            ):
                continue
            place = metadata["location"]
            dimension = place.get("dimensionRange", {})
            kind = (
                "ROW"
                if dimension.get("dimension") == "ROWS"
                else "SHEET"
                if "sheetId" in place
                else "SPREADSHEET"
            )
            if query.get("locationType", kind) != kind:
                continue
            sheet_id = place.get("sheetId", dimension.get("sheetId"))
            if (
                "metadataLocation" in query
                and sheet_id != query["metadataLocation"]["sheetId"]
            ):
                continue
            matches.append(mid)
        return matches

    def _select(self, data_filter):
        return [
            (
                self.metadata[mid]["location"]["dimensionRange"]["sheetId"],
                self.metadata[mid]["location"]["dimensionRange"]["startIndex"],
            )
            for mid in self._matched_metadata(data_filter)
            if "dimensionRange" in self.metadata[mid]["location"]
        ]

    def _read_ranges(self, filters):
        ranges = []
        for data_filter in filters:
            if "gridRange" in data_filter:
                sid = data_filter["gridRange"]["sheetId"]
                if sid not in self.sheets:
                    raise api_error(400)
                rows = copy.deepcopy(self.sheets[sid]["rows"])
                while rows and not any(rows[-1]):
                    rows.pop()
                ranges.append(
                    {
                        "valueRange": {"values": rows},
                        "dataFilters": [copy.deepcopy(data_filter)],
                    }
                )
            else:
                for sid, row in self._select(data_filter):
                    values = copy.deepcopy(self.sheets[sid]["rows"][row])
                    ranges.append(
                        {
                            "valueRange": {"values": [values] if any(values) else []},
                            "dataFilters": [copy.deepcopy(data_filter)],
                        }
                    )
        return {"valueRanges": ranges}

    def sheets_request(self, method, suffix, body=None):
        with self.lock:
            self.calls.append((method, suffix, copy.deepcopy(body)))
            if method == "get" and suffix == "?fields=sheets.properties":
                return {
                    "sheets": [
                        {
                            "properties": {
                                "sheetId": sid,
                                "title": self.sheets[sid]["title"],
                                "index": index,
                                "gridProperties": copy.deepcopy(
                                    self.sheets[sid]["gridProperties"]
                                ),
                            }
                        }
                        for index, sid in enumerate(self.sheet_order)
                    ]
                }
            if method == "get" and suffix.startswith("/developerMetadata/"):
                item = self.metadata.get(int(suffix.rsplit("/", 1)[1]))
                if item is None:
                    raise api_error(404)
                return copy.deepcopy(item)
            assert body is not None
            if suffix == "/developerMetadata:search":
                ids = {
                    mid
                    for data_filter in body["dataFilters"]
                    for mid in self._matched_metadata(data_filter)
                }
                return {
                    "matchedDeveloperMetadata": [
                        {"developerMetadata": copy.deepcopy(self.metadata[mid])}
                        for mid in sorted(ids)
                    ]
                }
            if suffix == "/values:batchGetByDataFilter":
                return self._read_ranges(body["dataFilters"])
            if self.before_write is not None:
                callback, self.before_write = self.before_write, None
                callback()
            if suffix == ":batchUpdate":
                previous = copy.deepcopy((self.sheets, self.metadata, self.sheet_order))
                try:
                    replies = [
                        self._apply(request) or {} for request in body["requests"]
                    ]
                except Exception:
                    self.sheets, self.metadata, self.sheet_order = previous
                    raise
                response = {"replies": replies}
            elif suffix == "/values:batchUpdateByDataFilter":
                updated = 0
                for entry in body["data"]:
                    for sheet_id, index in self._select(entry["dataFilter"]):
                        values = entry["values"][0]
                        row = self.sheets[sheet_id]["rows"][index]
                        row[: len(values)] = values
                        updated += 1
                response = {"totalUpdatedRows": updated}
            else:
                raise AssertionError(f"Unexpected Sheets request: {method} {suffix}")
            if self.fail_after == suffix:
                self.fail_after = None
                raise ConnectionError("Server committed; response was lost")
            return response

    def _apply(self, request):
        if "addSheet" in request:
            props = request["addSheet"]["properties"]
            if props["sheetId"] in self.sheets or any(
                s["title"] == props["title"] for s in self.sheets.values()
            ):
                raise api_error(400)
            index = props.get("index", len(self.sheet_order))
            if not 0 <= index <= len(self.sheet_order):
                raise api_error(400)
            self.sheets[props["sheetId"]] = {
                "title": props["title"],
                "rows": [],
                "gridProperties": copy.deepcopy(props["gridProperties"]),
            }
            self.sheet_order.insert(index, props["sheetId"])
        elif "createDeveloperMetadata" in request:
            item = request["createDeveloperMetadata"]["developerMetadata"]
            if item["metadataId"] in self.metadata:
                raise api_error(400)
            location = item["location"]
            sid = location.get(
                "sheetId", location.get("dimensionRange", {}).get("sheetId")
            )
            if sid is not None and sid not in self.sheets:
                raise api_error(400)
            self.metadata[item["metadataId"]] = copy.deepcopy(item)
        elif "deleteDeveloperMetadata" in request:
            for mid in self._matched_metadata(
                request["deleteDeveloperMetadata"]["dataFilter"]
            ):
                del self.metadata[mid]
        elif "updateDeveloperMetadata" in request:
            update = request["updateDeveloperMetadata"]
            assert update["fields"] == "metadataValue"
            ids = {
                mid
                for data_filter in update["dataFilters"]
                for mid in self._matched_metadata(data_filter)
            }
            for mid in ids:
                self.metadata[mid]["metadataValue"] = update["developerMetadata"][
                    "metadataValue"
                ]
            return {
                "updateDeveloperMetadata": {
                    "developerMetadata": [
                        copy.deepcopy(self.metadata[mid]) for mid in sorted(ids)
                    ]
                }
            }
        elif "appendDimension" in request:
            operation = request["appendDimension"]
            assert operation["dimension"] == "ROWS"
            if operation["sheetId"] not in self.sheets:
                raise api_error(400)
            self.sheets[operation["sheetId"]]["gridProperties"]["rowCount"] += (
                operation["length"]
            )
        elif "deleteSheet" in request:
            self.delete_sheet(request["deleteSheet"]["sheetId"])
        elif "insertDimension" in request:
            dimension = request["insertDimension"]["range"]
            assert dimension["dimension"] == "ROWS"
            if dimension["sheetId"] not in self.sheets:
                raise api_error(400)
            self.insert_row(dimension["sheetId"], dimension["startIndex"], [])
        elif "updateCells" in request:
            update = request["updateCells"]
            start = update["start"]
            self.sheets[start["sheetId"]]["rows"][start["rowIndex"]] = [
                cell["userEnteredValue"]["stringValue"]
                for cell in update["rows"][0]["values"]
            ]
        elif "updateDimensionProperties" not in request:
            raise AssertionError(f"Unexpected batch operation: {request}")
        return None
