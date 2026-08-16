import json

from slack_sdk.errors import SlackApiError

from handler.bigchat.create_bigchat_sheet import bigchat_created_message
from util.bigchat_event import parse_sheet_name
from util.utils import strip_multiline

# Slack 앱 설정(Interactivity & Shortcuts)에 등록된 message shortcut의 callback ID
CREATE_BIGCHAT_SHORTCUT_ID = "create_bigchat"
CREATE_BIGCHAT_VIEW_ID = "create_bigchat_modal"

NAME_BLOCK = "bigchat_name"
DATE_BLOCK = "bigchat_date"
START_BLOCK = "bigchat_start"
END_BLOCK = "bigchat_end"
ACTION_ID = "value"


def normalize_shortcut_body(body):
    """message shortcut payload를 기존 핸들러들이 쓰는 이벤트 모양(channel/ts/user가 문자열)으로 맞춘다.

    ts는 스레드 답글에서 실행해도 항상 스레드 첫 글을 가리킨다 (:gogo: 참여 흐름의 앵커).
    """
    message = body.get("message", {})
    return {
        **body,
        "channel": body["channel"]["id"],
        "ts": message.get("thread_ts") or message.get("ts"),
        "user": body["user"]["id"],
    }


def normalize_view_body(body):
    """view_submission payload의 private_metadata(채널/스레드 정보)를 최상위 키로 풀어놓는다."""
    metadata = json.loads(body["view"]["private_metadata"])
    return {
        **body,
        "channel": metadata["channel"],
        "ts": metadata["thread_ts"],
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


class SubmitCreateBigchatModal:
    def __init__(self, event, ack, slack_client, gs_client):
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

    def run(self):
        sheet_name = f"{self.name} {self.date[2:]} {self.start}~{self.end}"
        errors = self._validate(sheet_name)
        if errors:
            self.ack(response_action="errors", errors=errors)
            return False
        self.ack()  # 3초 안에 응답해야 하므로 시트 생성 전에 모달부터 닫는다

        worksheet_id = self.gs_client.create_bigchat_sheet(sheet_name)
        sheet_url = self.gs_client.get_url(worksheet_id)
        try:
            self.slack_client.send_thread_message(
                msg=bigchat_created_message(sheet_url, sheet_name),
                channel=self.channel,
                ts=self.thread_ts,
            )
        except SlackApiError as ex:
            if ex.response["error"] not in ("not_in_channel", "channel_not_found"):
                raise
            self._notify_bot_not_in_channel(sheet_url, sheet_name)
        return True

    def _validate(self, sheet_name):
        errors = {}
        if not self.name:
            errors[NAME_BLOCK] = "이름을 입력해줘!"
        if self.end <= self.start:
            errors[END_BLOCK] = "종료 시각은 시작 시각보다 늦어야 해!"
        if not errors and not parse_sheet_name(sheet_name):
            # 위젯이 날짜/시각 형식을 보장하므로 여기 올 일이 없지만, 방어적으로 남겨둔다
            errors[NAME_BLOCK] = "형식이 올바르지 않아. 입력값을 다시 확인해줘!"
        return errors

    def _notify_bot_not_in_channel(self, sheet_url, sheet_name):
        # 봇이 채널에 없으면 스레드 답글은 못 달지만, response_url로는 실행한 사람에게 안내할 수 있다
        self.slack_client.send_response_url_message(
            response_url=self.response_url,
            msg=strip_multiline(
                f"""
                시트(<{sheet_url}|{sheet_name}>)는 만들었는데, 내가 이 채널에 없어서 스레드에 답글을 못 달았어.
                나를 채널에 초대한 뒤 위 시트 링크를 스레드에 공유해줘. 그래야 이모지로 참여 신청을 받을 수 있어!"""
            ),
        )
