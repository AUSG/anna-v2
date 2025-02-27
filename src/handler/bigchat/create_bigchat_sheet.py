from handler.bigchat.mention_handler import MentionHandler


class CreateBigchatSheet(MentionHandler):
    def __init__(self, event, slack_client, gs_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client
        self.gs_client = gs_client

    def handle_mention(self):
        if not self.can_handle():
            return False

        sheet_name = self.text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        if not sheet_name:
            self.slack_client.send_message(msg="시트 이름이 입력되지 않았어. 다시 입력해줘!", ts=self.ts)
            return False

        worksheet_id = self.gs_client.create_bigchat_sheet(sheet_name)
        sheet_url = self.gs_client.get_url(worksheet_id)
        self.slack_client.send_message(
            msg=f"새로운 빅챗, 등록 완료! <{sheet_url}|{sheet_name}> :google_spreadsheets:",
            ts=self.ts,
        )
        return True

    def can_handle(self):
        return "새로운 빅챗" in self.text
