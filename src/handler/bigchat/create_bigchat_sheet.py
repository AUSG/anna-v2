from implementation.slack_client import Reaction
from implementation.member_finder import MemberManager, MemberNotFound, MemberLackInfo


class CreateBigchatSheet:
    def __init__(self, event, slack_client, gs_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client
        self.gs_client = gs_client

    def run(self):
        if "새로운 빅챗" not in self.text:
            return False

        # TODO: REGEX로 더 깔끔하게 따올 수 있지 않을까?
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

        # 빅챗 시트가 생성되기 이전에 등록을 시도한(GOGO 이모지를 누른)
        # 인원들이 누락된 것에 대한 사후처리
        channel = self.slack_client.get_channel()
        assert channel is not None
        reaction = self.slack_client.get_emoji(
            channel=channel,
            timestamp=self.ts,
        )
        if reaction is not None:
            reaction: Reaction
            for user in reaction.users:
                error_message = None
                try:
                    member = MemberManager.get_instance().find(user)
                except MemberNotFound:
                    error_message = f"<@{user}>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!"
                except MemberLackInfo:
                    error_message = f"<@{user}>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!"
                else:
                    self.gs_client.append_row(worksheet_id, member.transform_for_spreadsheet())
                finally:
                    if error_message:
                        self.slack_client.send_message(msg=error_message, ts=self.ts)
        return True
