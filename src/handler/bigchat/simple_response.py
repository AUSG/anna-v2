class SimpleResponse:
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def run(self):
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        if text:
            return False

        self.slack_client.send_message(msg="?", ts=self.ts)
        return True
