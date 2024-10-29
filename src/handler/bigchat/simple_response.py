from handler.bigchat.mention_handler import MentionHandler


class SimpleResponse(MentionHandler):
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def handle_mention(self):
        self.slack_client.send_message(
            msg="앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!", ts=self.ts
        )
        return True

    def can_handle(self):
        return True
