import json

from slack_sdk.errors import SlackApiError

from features.bigchat.models import CreateBigchatCommand, InvalidBigchatName
from features.bigchat.presentation.messages import (
    bigchat_created_message,
    bot_not_in_channel_message,
)
from features.bigchat.services.creation import register_early_reacted_users
from integrations.bigchat_repository import SpreadsheetBigchatRepository

# 슬랙 단축메뉴에 등록한 callback ID
CREATE_BIGCHAT_SHORTCUT_ID = "create_bigchat"
CREATE_BIGCHAT_VIEW_ID = "create_bigchat_modal"

NAME_BLOCK = "bigchat_name"
DATE_BLOCK = "bigchat_date"
START_BLOCK = "bigchat_start"
END_BLOCK = "bigchat_end"
ACTION_ID = "value"


def normalize_shortcut_body(body):
    """단축메뉴 입력을 기존 이벤트 형식으로 맞춘다. ts는 모집글 기준이다."""
    message = body.get("message", {})
    return {
        **body,
        "channel": body["channel"]["id"],
        "ts": message.get("thread_ts") or message.get("ts"),
        "user": body["user"]["id"],
    }


class OpenCreateBigchatModal:
    def __init__(self, event, web_client):
        self.trigger_id = event["trigger_id"]
        self.channel = event["channel"]
        self.thread_ts = event["ts"]
        self.response_url = event.get("response_url", "")
        self.web_client = web_client

    def run(self):
        self.web_client.views_open(trigger_id=self.trigger_id, view=self._build_view())
        return True

    def _build_view(self):
        return {
            "type": "modal",
            "callback_id": CREATE_BIGCHAT_VIEW_ID,
            # 제출 시점에 스레드 답글을 달 수 있도록 실행 컨텍스트를 실어 보낸다
            "private_metadata": json.dumps(
                {
                    "channel": self.channel,
                    "thread_ts": self.thread_ts,
                    "response_url": self.response_url,
                }
            ),
            "title": {"type": "plain_text", "text": "새로운 빅챗"},
            "submit": {"type": "plain_text", "text": "만들기"},
            "close": {"type": "plain_text", "text": "취소"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": NAME_BLOCK,
                    "label": {"type": "plain_text", "text": "이름"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": ACTION_ID,
                        # 구글 시트 탭 이름 100자 제한에서 날짜/시각(21자) 몫을 뺀 안전선
                        "max_length": 70,
                        "placeholder": {"type": "plain_text", "text": "예) AI 밋업"},
                    },
                },
                {
                    "type": "input",
                    "block_id": DATE_BLOCK,
                    "label": {"type": "plain_text", "text": "날짜"},
                    "element": {"type": "datepicker", "action_id": ACTION_ID},
                },
                {
                    "type": "input",
                    "block_id": START_BLOCK,
                    "label": {"type": "plain_text", "text": "시작 시각"},
                    "element": {"type": "timepicker", "action_id": ACTION_ID},
                },
                {
                    "type": "input",
                    "block_id": END_BLOCK,
                    "label": {"type": "plain_text", "text": "종료 시각"},
                    "element": {"type": "timepicker", "action_id": ACTION_ID},
                },
            ],
        }


def normalize_view_body(body):
    """모달의 채널과 모집글 정보를 이벤트로 옮긴다."""
    metadata = json.loads(body["view"]["private_metadata"])
    return {
        **body,
        "channel": metadata["channel"],
        "ts": metadata["thread_ts"],
        "user": body["user"]["id"],
    }


class SubmitCreateBigchatModal:
    def __init__(
        self, event, ack, slack_client, gs_client, member_manager, target_emoji
    ):
        metadata = json.loads(event["view"]["private_metadata"])
        values = event["view"]["state"]["values"]
        self.channel = metadata["channel"]
        self.thread_ts = metadata["thread_ts"]
        self.response_url = metadata.get("response_url", "")
        self.name = (values[NAME_BLOCK][ACTION_ID]["value"] or "").strip()
        self.date = values[DATE_BLOCK][ACTION_ID]["selected_date"]  # YYYY-MM-DD
        self.start = values[START_BLOCK][ACTION_ID]["selected_time"]  # HH:mm
        self.end = values[END_BLOCK][ACTION_ID]["selected_time"]  # HH:mm
        self.ack = ack
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.target_emoji = target_emoji
        self._bigchats = SpreadsheetBigchatRepository(gs_client)

    def run(self):
        sheet_name = f"{self.name} {self.date[2:]} {self.start}~{self.end}"
        errors = self._validate_fields()
        if errors:
            self.ack(response_action="errors", errors=errors)
            return False

        try:
            command = CreateBigchatCommand(sheet_name)
        except InvalidBigchatName:
            # 시트 이름 검증 실패를 모달 입력 오류로 알린다.
            errors = {NAME_BLOCK: "형식이 올바르지 않아. 입력값을 다시 확인해줘!"}
        else:
            self.ack()  # 3초 안에 응답하도록 시트 생성 전에 모달을 닫는다.
            return self._create_and_notify(command)

        self.ack(response_action="errors", errors=errors)
        return False

    def _validate_fields(self) -> dict[str, str]:
        errors = {}
        if not self.name:
            errors[NAME_BLOCK] = "이름을 입력해줘!"
        if self.end <= self.start:
            errors[END_BLOCK] = "종료 시각은 시작 시각보다 늦어야 해!"
        return errors

    def _create_and_notify(self, command: CreateBigchatCommand) -> bool:
        created = self._bigchats.create(
            command.sheet_name, channel=self.channel, thread_ts=self.thread_ts
        )
        try:
            self.slack_client.send_thread_message(
                msg=bigchat_created_message(created.sheet_url, created.sheet_name),
                channel=self.channel,
                ts=self.thread_ts,
            )
        except SlackApiError as ex:
            if ex.response["error"] not in ("not_in_channel", "channel_not_found"):
                raise
            # 채널 밖에서는 반응을 읽지 못해 일괄 등록을 건너뛴다.
            self._notify_bot_not_in_channel(created.sheet_url, created.sheet_name)
            return True

        register_early_reacted_users(
            self.slack_client,
            self.gs_client,
            self.member_manager,
            self.target_emoji,
            created.worksheet_id,
            channel=self.channel,
            thread_ts=self.thread_ts,
        )
        return True

    def _notify_bot_not_in_channel(self, sheet_url, sheet_name):
        # 채널에 없어도 response_url로 요청자에게 안내한다.
        self.slack_client.send_response_url_message(
            response_url=self.response_url,
            msg=bot_not_in_channel_message(sheet_url, sheet_name),
        )
