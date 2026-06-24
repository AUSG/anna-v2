import re

from handler.bigchat.mention_handler import MentionHandler
from util.utils import strip_multiline


class ArpOtpResponse(MentionHandler):
    ANNA_MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")

    def __init__(self, event, slack_client, arp_otp):
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event["channel"]
        self.user_id = event["user"]
        self.slack_client = slack_client
        self.arp_otp = arp_otp

    def handle_mention(self):
        if not self.can_handle():
            return False

        try:
            login_url = self.arp_otp.issue_login_url(self.user_id)
        except ValueError:
            self.slack_client.send_message(
                msg="ARP OTP 설정이 아직 안 되어 있어. 운영진에게 알려줘!",
                ts=self.ts,
            )
            return False

        self.slack_client.send_message_only_visible_to_user(
            msg=strip_multiline(
                """
                ARP 로그인 링크야.
                <{}|10분 안에 이 링크로 접속해줘!>

                링크는 본인에게만 보이고, 만료되면 `@ANNA otp`로 다시 발급받으면 돼.""",
                login_url,
            ),
            user_id=self.user_id,
            channel=self.channel,
            ts=self.ts,
        )
        return True

    def can_handle(self):
        text = self.ANNA_MENTION_PATTERN.sub("", self.text).strip().lower()
        return text == "otp"
