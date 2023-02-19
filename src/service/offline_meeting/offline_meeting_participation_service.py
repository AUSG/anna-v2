import logging
from threading import Lock
from dataclasses import dataclass

from slack_bolt import Say
from slack_sdk import WebClient

from configuration import Configs
from implementation import GoogleSpreadsheetClient, SlackClient
from util import get_prop, SlackGeneralEvent
from .action_commander import ActionCommander, TargetEvent, RejectCondition, ActionCommand
from .member_finder import MemberFinder
from .worksheet_finder import WorksheetMaker

ANNOUNCEMENT_CHANNEL_ID = Configs.ANNOUNCEMENT_CHANNEL_ID
ANNA_ID = Configs.ANNA_ID
ORGANIZER_ID = Configs.ORGANIZER_ID
SUBMIT_FORM_EMOJI = Configs.SUBMIT_FORM_EMOJI
SUSPEND_FORM_EMOJI = Configs.SUSPEND_FORM_EMOJI
MEMBERS_INFO_WORKSHEET_ID = Configs.MEMBERS_INFO_WORKSHEET_ID
FORM_SPREADSHEET_ID = Configs.FORM_SPREADSHEET_ID

ONE_WEEK = 60 * 60 * 24 * 7

PARTICIPATE_SINGLE_LOCK: Lock = Lock()


@dataclass
class EmojiAddedEvent:
    ts: str
    channel: str
    user: str


def participate_offline_meeting(event: SlackGeneralEvent, say: Say, web_client: WebClient):
    slack_client = SlackClient(say, web_client)
    action_commander = ActionCommander(event, slack_client)
    gs_client = GoogleSpreadsheetClient(slack_client)
    member_finder = MemberFinder(gs_client)
    worksheet_maker = WorksheetMaker(slack_client, gs_client)
    service = OfflineMeetingParticipationService(event, action_commander, slack_client, gs_client, member_finder,
                                                 worksheet_maker,
                                                 PARTICIPATE_SINGLE_LOCK)

    service.run()


class OfflineMeetingParticipationService:
    def __init__(self, raw_event: SlackGeneralEvent, action_commander: ActionCommander, slack_client: SlackClient,
                 gs_client: GoogleSpreadsheetClient, member_finder: MemberFinder, worksheet_maker: WorksheetMaker,
                 participate_single_lock: Lock):
        self.event = EmojiAddedEvent(get_prop(raw_event, 'item', 'ts'), get_prop(raw_event, 'item', 'channel'),
                                     get_prop(raw_event, 'user'))
        self.action_commander = action_commander
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_finder = member_finder
        self.worksheet_maker = worksheet_maker
        self.participate_single_lock = participate_single_lock

    def run(self):
        if not self._is_target_event():
            return

        member = self._find_member_info()

        self._participate(member)

    def _is_target_event(self):
        target_event = TargetEvent(SUBMIT_FORM_EMOJI, ANNOUNCEMENT_CHANNEL_ID)
        reject_condition = RejectCondition(SUSPEND_FORM_EMOJI, ORGANIZER_ID)

        command = self.action_commander.decide(target_event, reject_condition)

        if command == ActionCommand.NOOP:
            return False
        elif command == ActionCommand.REJECT:
            self.slack_client.tell(msg=f"오거나이저가 :stop2: 이모지를 붙여놨기 때문에 <@{self.event.user}>의 요청을 들어줄 수가 없어.",
                                   ts=self.event.ts)
            return False
        else:
            return True

    def _find_member_info(self):
        member = self.member_finder.find(self.event.user)
        return member

    def _participate(self, member):
        # 워크시트 생성 동시성 이슈를 제어하기위해 thread lock
        with self.participate_single_lock:
            try:
                is_new, worksheet_id = self.worksheet_maker.find_or_create_worksheet(
                    self.event.ts,
                    self.event.channel,
                    FORM_SPREADSHEET_ID,
                )

                self.gs_client.append_row(FORM_SPREADSHEET_ID, worksheet_id, member.to_list())
                if is_new:
                    self.slack_client.tell(
                        msg=f"새로운 시트를 만들었어! <{self.gs_client.get_url(FORM_SPREADSHEET_ID, worksheet_id)}|구글스프레드 시트>",
                        ts=self.event.ts)

                self.slack_client.tell(msg=f"<@{self.event.user}>, 등록 완료!", ts=self.event.ts)

                self.slack_client.send_only_visible_target_user_message_to_thread(
                    msg=f"<@{self.event.user}> 네 정보를 {member.phone} / {member.email} / {member.school_name_or_company_name} / 로 입력했어. 바뀐 부분이 있다면 이 스레드에 남겨줘!",
                    channel=self.event.channel,
                    thread_ts=self.event.ts,
                    user=self.event.user,
                )


            except Exception as e:
                logging.error("fail OfflineMeetingParticipationService._participate()")
                raise e
