import logging
import os
from dataclasses import dataclass

from slack_bolt import Say
from slack_sdk import WebClient

from expiringdict import ExpiringDict
from implementation import GoogleSpreadsheetClient, SlackClient
from util import get_prop, SlackGeneralEvent
from .action_commander import ActionCommander, TargetEvent, RejectCondition, ActionCommand
from .member_finder import MemberFinder
from .worksheet_finder import WorksheetMaker

ANNOUNCEMENT_CHANNEL_ID = os.environ.get('ANNOUNCEMENT_CHANNEL_ID')
ANNA_ID = os.environ.get('ANNA_ID')
ORGANIZER_ID = os.environ.get('ORGANIZER_ID')
SUBMIT_FORM_EMOJI = os.environ.get('SUBMIT_FORM_EMOJI')
SUSPEND_FORM_EMOJI = os.environ.get('SUSPEND_FORM_EMOJI')
MEMBERS_INFO_WORKSHEET_ID = int(os.environ.get('MEMBERS_INFO_WORKSHEET_ID'))
FORM_SPREADSHEET_ID = os.environ.get('FORM_SPREADSHEET_ID')

ONE_WEEK = 60 * 60 * 24 * 7
WORKSHEET_ID_CACHE = ExpiringDict(max_len=100, max_age_seconds=ONE_WEEK)

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
                                                 worksheet_maker, WORKSHEET_ID_CACHE)

    service.run()


class OfflineMeetingParticipationService:
    def __init__(self, raw_event: SlackGeneralEvent, action_commander: ActionCommander, slack_client: SlackClient,
                 gs_client: GoogleSpreadsheetClient, member_finder: MemberFinder, worksheet_maker: WorksheetMaker,
                 is_exist_worksheet_cache: ExpiringDict):
        self.event = EmojiAddedEvent(get_prop(raw_event, 'item', 'ts'), get_prop(raw_event, 'item', 'channel'),
                                     get_prop(raw_event, 'user'))
        self.action_commander = action_commander
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_finder = member_finder
        self.worksheet_maker = worksheet_maker
        self.is_exist_worksheet_cache = is_exist_worksheet_cache

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
        try:
            is_new, worksheet_id = self.worksheet_maker.find_or_create_worksheet(
                self.event.ts,
                self.event.channel,
                FORM_SPREADSHEET_ID,
            )

            self.gs_client.append_row(FORM_SPREADSHEET_ID, worksheet_id, member.to_list())
            if is_new and not self.is_exist_worksheet_cache.get(worksheet_id):
                self.slack_client.tell(
                    msg=f"새로운 시트를 만들었어! <{self.gs_client.get_url(FORM_SPREADSHEET_ID, worksheet_id)}|구글스프레드 시트>",
                    ts=self.event.ts)

                self.is_exist_worksheet_cache[worksheet_id] = True

            self.slack_client.tell(msg=f"<@{self.event.user}>, 등록 완료!", ts=self.event.ts)

        except Exception as e:
            logging.error("fail OfflineMeetingParticipationService._participate()")
            raise e
