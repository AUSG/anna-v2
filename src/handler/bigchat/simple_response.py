from handler.bigchat.mention_handler import MentionHandler


class SimpleResponse(MentionHandler):
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def handle_mention(self) -> str:
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        if text:
            return False

        self.slack_client.send_message(msg="?", ts=self.ts)
        return True

    def can_handle(self):
        return True
