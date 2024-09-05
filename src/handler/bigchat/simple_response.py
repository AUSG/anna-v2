import random
import re


class SimpleResponse:
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def run(self):
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        if self._is_shuffle_trigger(text):
            shuffled = self._shuffle(text)
            self.slack_client.send_message(msg=shuffled, ts=self.ts)
        else:
            self.slack_client.send_message(msg="?", ts=self.ts)
        return True

    def _is_shuffle_trigger(self, text):
        if "섞어줘" in text or "shuffle" in text.lower():
            return True

    def _shuffle(self, text):
        # 유저 이름들을 정규표현식 (<@Uxxx>) 로 추출하고 셔플한 뒤 스트링화
        users = re.findall(r'<@U[0-9a-zA-Z]+>', text)
        random.shuffle(users)
        return "여기있어!\n" + " ".join(users)
