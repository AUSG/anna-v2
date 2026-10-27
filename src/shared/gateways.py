"""기능이 외부 세계에 요구하는 계약. 구현은 integrations/ 에 있다.

여기 메서드는 예외 대신 값으로 결과를 돌려준다. 네트워크 장애처럼 복구 불가능한
오류만 예외로 올라가고, 진입점의 오류 경계가 그것을 관리자에게 알린다.
"""

from enum import Enum, auto
from typing import List, Optional, Protocol, Tuple

from shared.slack_models import Message, Reaction


class AppendOutcome(Enum):
    ADDED = auto()
    ALREADY_PRESENT = auto()
    WORKSHEET_MISSING = auto()


class SheetsGateway(Protocol):
    def list_worksheets(self) -> List[Tuple[int, str]]:
        ...

    def get_values(
        self, worksheet_id: int, cell_range: Optional[str] = None
    ) -> List[List[str]]:
        """워크시트가 없으면 빈 목록."""
        ...

    def append_row_if_absent(
        self, worksheet_id: int, values: List[str]
    ) -> AppendOutcome:
        ...

    def delete_row(self, worksheet_id: int, query: str) -> bool:
        """query 와 일치하는 첫 셀의 행을 지운다. 워크시트가 없으면 False."""
        ...

    def get_worksheet_title(self, worksheet_id: int) -> Optional[str]:
        """워크시트가 없으면 None."""
        ...

    def create_bigchat_sheet(self, title: str) -> int:
        ...

    def get_url(self, worksheet_id: int) -> str:
        ...


class SlackGateway(Protocol):
    def send_thread_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[dict]] = None,
    ) -> None:
        ...

    def send_channel_message(self, channel: str, text: str) -> None:
        ...

    def send_markdown(self, channel: str, text: str) -> None:
        ...

    def send_answer(
        self, channel: str, ts: str, answer: str, sources: List[str]
    ) -> None:
        ...

    def send_direct_message(self, user_id: str, text: str) -> None:
        ...

    def send_ephemeral(
        self,
        channel: str,
        user_id: str,
        text: str,
        ts: Optional[str] = None,
        blocks: Optional[List[dict]] = None,
    ) -> None:
        ...

    def send_response_url_message(self, response_url: str, text: str) -> None:
        ...

    def get_thread(self, channel: str, thread_ts: str) -> List[Message]:
        """스레드 첫 글부터 첫 페이지까지. 페이지네이션은 하지 않는다."""
        ...

    def get_thread_of_message(self, channel: str, ts: str) -> List[Message]:
        """ts 메시지가 속한 스레드. 답글이 없으면 그 메시지 하나만 담긴다."""
        ...

    def get_reaction(
        self, channel: str, ts: str, emoji_name: str
    ) -> Optional[Reaction]:
        ...

    def get_permalink(self, channel: str, ts: str) -> Optional[str]:
        ...

    def add_reaction(self, channel: str, ts: str, emoji_name: str) -> None:
        ...

    def remove_reaction(self, channel: str, ts: str, emoji_name: str) -> None:
        ...

    def download_file(self, url: str) -> Optional[bytes]:
        ...

    def open_view(self, trigger_id: str, view: dict) -> None:
        ...
