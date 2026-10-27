"""빅챗 Slack 진입점: 생성 멘션, 모달, 참여/취소 반응과 수동 리마인더."""

import json
import logging
import re

from slack_sdk.errors import SlackApiError

from features.bigchat.models import (
    CreateBigchatCommand,
    InvalidBigchatName,
    ReminderResult,
)
from features.bigchat.presentation.messages import (
    bigchat_created_message,
    bot_not_in_channel_message,
    invalid_bigchat_name_message,
)
from features.bigchat.presentation.modals import (
    ACTION_ID,
    CREATE_BIGCHAT_SHORTCUT_ID,
    CREATE_BIGCHAT_VIEW_ID,
    DATE_BLOCK,
    END_BLOCK,
    NAME_BLOCK,
    START_BLOCK,
    create_bigchat_view,
)
from features.bigchat.presentation.reminders import (
    BROADCAST_PHRASE,
    TEST_PHRASE,
    USAGE,
    build_report,
    missing_targets_message,
)
from features.bigchat.services.cancellation import AbandonBigchat
from features.bigchat.services.creation import (
    create_bigchat,
    register_early_reacted_users,
)
from features.bigchat.services.registration import JoinBigchat
from features.bigchat.services.reminders import RemindBigchat
from integrations.bigchat_repository import SpreadsheetBigchatRepository
from shared.slack_commands import MentionHandler
from shared.slack_middleware import catch_global_error
from slack_router import matches_mention

logger = logging.getLogger(__name__)
SLACK_USER_PAT = re.compile(r"<@([A-Z0-9]+)>")


class CreateBigchatSheet(MentionHandler):
    def __init__(self, event, slack_client, gs_client, member_manager, target_emoji):
        self.text = event["text"]
        self.ts = event["ts"]
        self.thread_ts = event.get("thread_ts")
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.target_emoji = target_emoji
        self._bigchats = SpreadsheetBigchatRepository(gs_client)

    def handle_mention(self):
        if not self.can_handle():
            return False
        sheet_name = self.text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        try:
            command = CreateBigchatCommand(sheet_name)
        except InvalidBigchatName:
            command = None
        if command is None:
            self.slack_client.send_message_only_visible_to_user(
                msg=invalid_bigchat_name_message(self.user),
                channel=self.channel,
                ts=self.ts,
                user_id=self.user,
            )
            return False
        created = create_bigchat(command, self._bigchats)
        self.slack_client.send_message(
            msg=bigchat_created_message(created.sheet_url, created.sheet_name),
            ts=self.ts,
        )
        register_early_reacted_users(
            self.slack_client,
            self.gs_client,
            self.member_manager,
            self.target_emoji,
            created.worksheet_id,
            channel=self.channel,
            thread_ts=self.thread_ts or self.ts,
        )
        return True

    def can_handle(self):
        return matches_mention("create_bigchat", self.text)


def normalize_shortcut_body(body):
    message = body.get("message", {})
    return {
        **body,
        "channel": body["channel"]["id"],
        "ts": message.get("thread_ts") or message.get("ts"),
        "user": body["user"]["id"],
    }


def normalize_view_body(body):
    metadata = json.loads(body["view"]["private_metadata"])
    return {
        **body,
        "channel": metadata["channel"],
        "ts": metadata["thread_ts"],
        "user": body["user"]["id"],
    }


class OpenCreateBigchatModal:
    def __init__(self, event, web_client):
        self.trigger_id = event["trigger_id"]
        self.channel = event["channel"]
        self.thread_ts = event["ts"]
        self.response_url = event.get("response_url", "")
        self.web_client = web_client

    def run(self):
        self.web_client.views_open(trigger_id=self.trigger_id, view=self._build_view())
        return True

    def _build_view(self):
        return create_bigchat_view(self.channel, self.thread_ts, self.response_url)


class SubmitCreateBigchatModal:
    def __init__(
        self, event, ack, slack_client, gs_client, member_manager, target_emoji
    ):
        metadata = json.loads(event["view"]["private_metadata"])
        values = event["view"]["state"]["values"]
        self.channel = metadata["channel"]
        self.thread_ts = metadata["thread_ts"]
        self.response_url = metadata.get("response_url", "")
        self.name = (values[NAME_BLOCK][ACTION_ID]["value"] or "").strip()
        self.date = values[DATE_BLOCK][ACTION_ID]["selected_date"]
        self.start = values[START_BLOCK][ACTION_ID]["selected_time"]
        self.end = values[END_BLOCK][ACTION_ID]["selected_time"]
        self.ack = ack
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.target_emoji = target_emoji
        self._bigchats = SpreadsheetBigchatRepository(gs_client)

    def run(self):
        sheet_name = f"{self.name} {self.date[2:]} {self.start}~{self.end}"
        errors = self._validate_fields()
        if errors:
            self.ack(response_action="errors", errors=errors)
            return False
        try:
            command = CreateBigchatCommand(sheet_name)
        except InvalidBigchatName:
            errors = {NAME_BLOCK: "형식이 올바르지 않아. 입력값을 다시 확인해줘!"}
        else:
            self.ack()
            return self._create_and_notify(command)
        self.ack(response_action="errors", errors=errors)
        return False

    def _validate_fields(self) -> dict[str, str]:
        errors = {}
        if not self.name:
            errors[NAME_BLOCK] = "이름을 입력해줘!"
        if self.end <= self.start:
            errors[END_BLOCK] = "종료 시각은 시작 시각보다 늦어야 해!"
        return errors

    def _create_and_notify(self, command: CreateBigchatCommand) -> bool:
        created = create_bigchat(command, self._bigchats)
        try:
            self.slack_client.send_thread_message(
                msg=bigchat_created_message(created.sheet_url, created.sheet_name),
                channel=self.channel,
                ts=self.thread_ts,
            )
        except SlackApiError as ex:
            if ex.response["error"] not in ("not_in_channel", "channel_not_found"):
                raise
            self._notify_bot_not_in_channel(created.sheet_url, created.sheet_name)
            return True
        register_early_reacted_users(
            self.slack_client,
            self.gs_client,
            self.member_manager,
            self.target_emoji,
            created.worksheet_id,
            channel=self.channel,
            thread_ts=self.thread_ts,
        )
        return True

    def _notify_bot_not_in_channel(self, sheet_url, sheet_name):
        self.slack_client.send_response_url_message(
            response_url=self.response_url,
            msg=bot_not_in_channel_message(sheet_url, sheet_name),
        )


class RemindBigchatCommand(MentionHandler):
    def __init__(self, event, slack_client, gs_client, member_manager, anna_id):
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.anna_id = anna_id

    def can_handle(self):
        return matches_mention("reminder", self.text)

    def handle_mention(self):
        if not self.can_handle():
            return False
        if BROADCAST_PHRASE in self.text:
            return self._broadcast()
        if TEST_PHRASE in self.text:
            return self._test()
        self._reply(USAGE)
        return False

    def _broadcast(self):
        logger.warning(
            "Manual reminder BROADCAST triggered by %s — sending to every applicant",
            self.user,
        )
        result = self._run()
        self._reply(self._build_report(result, targets=None))
        return True

    def _test(self):
        targets = self._target_user_ids()
        if not targets:
            self._reply(missing_targets_message(self.user))
            return False
        logger.info(
            "Manual reminder test triggered by %s, targets=%s", self.user, targets
        )
        result = self._run(only_user_ids=targets)
        self._reply(self._build_report(result, targets))
        return True

    def _run(self, only_user_ids=None) -> ReminderResult:
        return RemindBigchat(
            self.slack_client, self.gs_client, self.member_manager
        ).run(only_user_ids=only_user_ids)

    def _target_user_ids(self):
        return [
            user_id
            for user_id in SLACK_USER_PAT.findall(self.text)
            if user_id != self.anna_id
        ]

    @staticmethod
    def _build_report(result: ReminderResult, targets) -> str:
        return build_report(result, targets)

    def _reply(self, msg: str):
        self.slack_client.send_message_only_visible_to_user(
            msg=msg, channel=self.channel, ts=self.ts, user_id=self.user
        )


@catch_global_error()
def join_bigchat(event, say, client, dependencies):
    settings = dependencies.envs
    slack_client = dependencies.SlackClient(say, client)
    JoinBigchat(
        event,
        settings.JOIN_BIGCHAT_EMOJI,
        slack_client,
        dependencies.GoogleSpreadsheetClient(),
        dependencies._get_member_manager(),
        loading_emoji=dependencies._loading_emoji(slack_client, event),
        public_base_url=settings.PUBLIC_BASE_URL,
        token_secret=settings.ICS_TOKEN_SECRET,
    ).run()


@catch_global_error()
def abandon_bigchat(event, say, client, dependencies):
    slack_client = dependencies.SlackClient(say, client)
    AbandonBigchat(
        event,
        dependencies.envs.ANNA_ID,
        dependencies.envs.JOIN_BIGCHAT_EMOJI,
        slack_client,
        dependencies._get_member_manager(),
        dependencies.GoogleSpreadsheetClient(),
        loading_emoji=dependencies._loading_emoji(slack_client, event),
    ).run()


@catch_global_error()
def open_create_bigchat_modal(event, say, client, dependencies):
    OpenCreateBigchatModal(event, client).run()


@catch_global_error()
def submit_create_bigchat_modal(event, say, client, ack, dependencies):
    SubmitCreateBigchatModal(
        event,
        ack,
        dependencies.SlackClient(say, client),
        dependencies.GoogleSpreadsheetClient(),
        dependencies._get_member_manager(),
        dependencies.envs.JOIN_BIGCHAT_EMOJI,
    ).run()


def register(app, dependencies):
    @app.event("reaction_added")
    def handle_reaction_added_event(ack, event, say, client):
        ack()
        join_bigchat(event=event, say=say, client=client, dependencies=dependencies)

    @app.event("reaction_removed")
    def handle_reaction_removed_event(ack, event, say, client):
        ack()
        abandon_bigchat(event=event, say=say, client=client, dependencies=dependencies)

    @app.action(re.compile("calendar_.*"))
    def handle_calendar_button(ack):
        ack()

    @app.shortcut(CREATE_BIGCHAT_SHORTCUT_ID)
    def handle_create_bigchat_shortcut(ack, body, say, client):
        ack()
        open_create_bigchat_modal(
            event=normalize_shortcut_body(body),
            say=say,
            client=client,
            dependencies=dependencies,
        )

    @app.view(CREATE_BIGCHAT_VIEW_ID)
    def handle_create_bigchat_view_submission(ack, body, say, client):
        submit_create_bigchat_modal(
            event=normalize_view_body(body),
            say=say,
            client=client,
            ack=ack,
            dependencies=dependencies,
        )
