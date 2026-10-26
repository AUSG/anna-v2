from dataclasses import dataclass

from util.bigchat_event import parse_sheet_name


class InvalidBigchatName(ValueError):
    pass


@dataclass(frozen=True)
class CreateBigchatCommand:
    sheet_name: str

    def __post_init__(self):
        # 시트 이름은 안내문에도 쓰이므로 검증할 때 원문을 바꾸지 않는다.
        if not parse_sheet_name(self.sheet_name):
            raise InvalidBigchatName(self.sheet_name)


@dataclass(frozen=True)
class BigchatCreated:
    worksheet_id: int
    sheet_name: str
    sheet_url: str
