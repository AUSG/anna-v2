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

    def add_legacy_sheet(self, worksheet_id, rows):
        self.sheets[worksheet_id] = {
            "title": "Legacy bigchat",
            "rows": copy.deepcopy(rows),
        }

    def insert_row(self, worksheet_id, index, values):
        self.sheets[worksheet_id]["rows"].insert(index, list(values))
        for metadata in self.metadata.values():
            location = metadata["location"].get("dimensionRange", {})
            if (
                location.get("sheetId") == worksheet_id
                and location["startIndex"] >= index
            ):
                location["startIndex"] += 1
                location["endIndex"] += 1

    def _select(self, data_filter):
        query = data_filter["developerMetadataLookup"]
        matches = []
        for metadata in self.metadata.values():
            if any(
                metadata.get(k) != query[k]
                for k in ("metadataId", "metadataKey", "metadataValue", "visibility")
                if k in query
            ):
                continue
            location = metadata["location"].get("dimensionRange", {})
            if not location or location.get("dimension") != "ROWS":
                continue
            if location["sheetId"] != query["metadataLocation"]["sheetId"]:
                continue
            matches.append((location["sheetId"], location["startIndex"]))
        return matches

    def sheets_request(self, method, suffix, body=None):
        with self.lock:
            self.calls.append((method, suffix, copy.deepcopy(body)))
            if method == "get" and suffix.startswith("/developerMetadata/"):
                item = self.metadata.get(int(suffix.rsplit("/", 1)[1]))
                if item is None:
                    raise api_error(404)
                return copy.deepcopy(item)
            assert body is not None
            if suffix == "/values:batchGetByDataFilter":
                return {
                    "valueRanges": [
                        {
                            "valueRange": {
                                "values": [copy.deepcopy(self.sheets[s]["rows"][r])]
                            }
                        }
                        for f in body["dataFilters"]
                        for s, r in self._select(f)
                    ]
                }
            if self.before_write is not None:
                callback, self.before_write = self.before_write, None
                callback()
            if suffix == ":batchUpdate":
                previous = copy.deepcopy((self.sheets, self.metadata))
                try:
                    for request in body["requests"]:
                        self._apply(request)
                except Exception:
                    self.sheets, self.metadata = previous
                    raise
                response = {"replies": [{} for _ in body["requests"]]}
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
            if props["sheetId"] in self.sheets:
                raise api_error(400)
            self.sheets[props["sheetId"]] = {"title": props["title"], "rows": []}
        elif "createDeveloperMetadata" in request:
            item = request["createDeveloperMetadata"]["developerMetadata"]
            if item["metadataId"] in self.metadata:
                raise api_error(400)
            self.metadata[item["metadataId"]] = copy.deepcopy(item)
        elif "insertDimension" in request:
            dimension = request["insertDimension"]["range"]
            assert dimension["dimension"] == "ROWS"
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
