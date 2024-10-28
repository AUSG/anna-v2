import random
import re
from handler.bigchat.mention_handler import MentionHandler


class ShuffleResponse(MentionHandler):
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def handle_mention(self):
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        shuffled = self._shuffle(text.replace("shuffle", "").replace("섞어줘", "").strip())
        self.slack_client.send_message(msg=shuffled, ts=self.ts)
        return True

    def can_handle(self):
        return "섞어줘" in self.text or "shuffle" in self.text.lower()

    def _shuffle(self, text):
        # 유저 이름들을 정규표현식 (<@Uxxx>) 로 추출하고 셔플한 뒤 스트링화
        users = re.findall(r"<@U[0-9a-zA-Z]+>", text)
        random.shuffle(users)
        return "여기있어!\n" + " ".join(users)
