"""빅챗 생성 모달의 Block Kit 표현."""

import json

CREATE_BIGCHAT_SHORTCUT_ID = "create_bigchat"
CREATE_BIGCHAT_VIEW_ID = "create_bigchat_modal"
NAME_BLOCK = "bigchat_name"
DATE_BLOCK = "bigchat_date"
START_BLOCK = "bigchat_start"
END_BLOCK = "bigchat_end"
ACTION_ID = "value"


def create_bigchat_view(channel, thread_ts, response_url):
    return {
        "type": "modal",
        "callback_id": CREATE_BIGCHAT_VIEW_ID,
        "private_metadata": json.dumps(
            {"channel": channel, "thread_ts": thread_ts, "response_url": response_url}
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
