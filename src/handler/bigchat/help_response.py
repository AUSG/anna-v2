from handler.bigchat.mention_handler import MentionHandler
from util.utils import strip_multiline


class HelpResponse(MentionHandler):
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def handle_mention(self):
        if not self.can_handle():
            return False
        self.slack_client.send_message(
            msg=strip_multiline(
                """
                나를 멘션했을 때, 사용할 수 있는 명령어야.
                - `shuffle` 또는 `섞어줘`: 멘션된 유저들을 섞어줘!
                - `새로운 빅챗`: 새로운 빅챗 시트를 만들어줘!
                (메시지 더보기 메뉴 `⋮` > `새로운 빅챗 만들기`로 폼 입력도 돼!)
                - `빅챗 리마인더 테스트 @누구`: 전날 저녁 6시에 나갈 리마인더 DM 을 지금 그 사람에게만 보내볼게!
                - `빅챗 리마인더 지금 전원 발송`: 내일 빅챗 신청자 전원에게 리마인더 DM 을 지금 보낼게!
                - `help` 또는 `도움`: 도움말을 보여줘!
                그 외에는 뭐든 물어봐 — 그냥 멘션하면서 질문하면 내가 아는 선에서 답해줄게!
                (`q)` 를 붙이면 위 명령어보다 질문을 우선해)
                더 많은 기능이 필요하면, https://github.com/AUSG/anna-v2 으로 기여해줘!"""
            ),
            ts=self.ts,
        )
        return True

    def can_handle(self):
        return "help" in self.text or "도움" in self.text.lower()
