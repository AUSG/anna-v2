import random
import re

from shared.mention_handler import MentionHandler
from slack_router import matches_mention


class ShuffleResponse(MentionHandler):
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def handle_mention(self):
        if not self.can_handle():
            return False
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        shuffled = self._shuffle(
            text.replace("shuffle", "").replace("섞어줘", "").strip()
        )
        self.slack_client.send_message(msg=shuffled, ts=self.ts)
        return True

    def can_handle(self):
        return matches_mention("shuffle", self.text)

    def _shuffle(self, text):
        # 유저 이름들을 정규표현식 (<@Uxxx>) 로 추출하고 셔플한 뒤 스트링화
        users = re.findall(r"<@U[0-9a-zA-Z]+>", text)
        random.shuffle(users)
        return "여기있어!\n" + " ".join(users)
