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
                - `help` 또는 `도움`: 도움말을 보여줘!
                더 많은 기능이 필요하면, https://github.com/AUSG/anna-v2 으로 기여해줘!"""
            ),
            ts=self.ts,
        )
        return True

    def can_handle(self):
        return "help" in self.text or "도움" in self.text.lower()
