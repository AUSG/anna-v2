from handler.bigchat.mention_handler import MentionHandler
from util.bigchat_event import parse_sheet_name
from util.utils import strip_multiline


class CreateBigchatSheet(MentionHandler):
    def __init__(self, event, slack_client, gs_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.gs_client = gs_client

    def handle_mention(self):
        if not self.can_handle():
            return False

        sheet_name = self.text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        if not parse_sheet_name(sheet_name):
            self.slack_client.send_message_only_visible_to_user(
                msg=strip_multiline(
                    f"""
                    <@{self.user}> 형식이 올바르지 않아서 빅챗을 만들지 않았어. 아래 형식으로 다시 입력해줘!
                    `새로운 빅챗 <이름> yy-MM-DD HH:mm~HH:mm`
                    예) `새로운 빅챗 AI 밋업 26-08-20 19:00~21:00`
                    (실제 존재하는 날짜/시각이어야 하고, 종료 시각은 시작보다 늦어야 해!)"""
                ),
                channel=self.channel,
                ts=self.ts,
                user_id=self.user,
            )
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
