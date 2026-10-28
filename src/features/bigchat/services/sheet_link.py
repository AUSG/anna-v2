import re
from collections.abc import Iterable

SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


def extract_worksheet_id(texts: Iterable[str]) -> int | None:
    for text in texts:
        pat = SPREADSHEET_PAT.search(text)
        if pat is not None and len(pat.groups()) > 0:
            return int(pat.groups()[0])
    return None
