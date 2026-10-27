"""빅챗 Slack 진입점: 생성 멘션, 모달, 참여/취소 반응과 수동 리마인더.

여기서만 Slack 페이로드를 해석하고 답글을 보낸다. 판단은 services/ 가, 문구는 presentation/ 이 맡는다.
"""

import logging
import re
from typing import List, Optional

from slack_sdk.errors import SlackApiError

from features.bigchat.models import (
    BigchatCreated,
    CancellationStatus,
    CreateBigchatCommand,
    RegistrationStatus,
    parse_sheet_name,
)
from features.bigchat.presentation.blocks import registration_blocks
from features.bigchat.presentation.messages import (
    bigchat_created_message,
    bot_not_in_channel_message,
    build_registration_info_message,
    cancellation_notice,
    cancelled_message,
    early_reactions_failed_message,
    early_reactions_registered_message,
    invalid_bigchat_name_message,
    registered_message,
    registration_notice,
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
    USAGE,
    build_report,
    missing_targets_message,
)
from features.bigchat.services.calendar import calendar_links
from features.bigchat.services.cancellation import cancel_registration
from features.bigchat.services.commands import CreateBigchat, Reminder
from features.bigchat.services.creation import create_bigchat
from features.bigchat.services.registration import register_applicant
from features.bigchat.services.reminders import RemindBigchat
from features.bigchat.services.sheet_link import extract_worksheet_id
from runtime import Runtime
from shared.error_boundary import report_failure
from shared.gateways import SlackGateway
from shared.loading_emoji import with_loading_emoji
from shared.slack_events import (
    MentionEvent,
    ReactionEvent,
    ShortcutPayload,
    ViewSubmission,
)
from shared.slack_models import Message

logger = logging.getLogger(__name__)


# --- 참여 / 취소 (reaction_added / reaction_removed) ---------------------------


def _bigchat_thread(
    event: ReactionEvent, slack: SlackGateway
) -> Optional[tuple[int, List[Message]]]:
    """반응이 달린 글이 빅챗 모집글(스레드 첫 글이고 시트 링크가 있음)일 때만 (시트 ID, 스레드)."""
    messages = slack.get_thread_of_message(event.channel, event.ts)
    if not messages or messages[0].ts != event.ts:
        return None
    worksheet_id = extract_worksheet_id(message.text for message in messages)
    if not worksheet_id:
        return None
    return worksheet_id, messages


def join_bigchat(event: ReactionEvent, slack: SlackGateway, runtime: Runtime) -> bool:
    settings = runtime.settings
    if event.kind != "reaction_added" or event.reaction != settings.JOIN_BIGCHAT_EMOJI:
        return False
    found = _bigchat_thread(event, slack)
    if found is None:
        return False
    worksheet_id, messages = found

    # 여기부터가 실제 동작이다. 위 검사들에서 걸러진 이벤트(관심 없는 이모지, 빅챗 글이
    # 아닌 메시지 등)에는 loading 이모지가 아예 붙지 않는다.
    def register() -> bool:
        registration = register_applicant(
            event.user, worksheet_id, runtime.members(), runtime.sheets()
        )
        if registration.status is not RegistrationStatus.REGISTERED:
            slack.send_thread_message(
                event.channel,
                event.ts,
                registration_notice(registration.status, event.user),
            )
            return registration.status is RegistrationStatus.ALREADY_REGISTERED
        slack.send_thread_message(
            event.channel, event.ts, registered_message(event.user)
        )
        msg = build_registration_info_message(event.user, registration.member)
        slack.send_ephemeral(
            event.channel,
            event.user,
            msg,
            ts=event.ts,
            blocks=_calendar_blocks(
                msg, worksheet_id, event, messages[0].text, slack, runtime
            ),
        )
        return True

    return with_loading_emoji(slack, event.channel, event.ts, register)


def _calendar_blocks(
    msg: str,
    worksheet_id: int,
    event: ReactionEvent,
    intro_text: str,
    slack: SlackGateway,
    runtime: Runtime,
) -> Optional[List[dict]]:
    """등록 성공 뒤 제공할 캘린더 안내. 구형식 시트 등 파싱 불가면 None. 부가 조회 실패는 등록을 실패시키지 않는다."""
    try:
        bigchat = parse_sheet_name(
            runtime.sheets().get_worksheet_title(worksheet_id) or ""
        )
    except Exception as ex:
        logger.warning(f"Failed to build calendar buttons: {ex}")
        return None
    if not bigchat:
        return None
    links = calendar_links(
        bigchat,
        worksheet_id,
        event.channel,
        event.ts,
        slack.get_permalink(event.channel, event.ts),
        intro_text,
        public_base_url=runtime.settings.PUBLIC_BASE_URL,
        token_secret=runtime.settings.ICS_TOKEN_SECRET,
    )
    return registration_blocks(msg, links.gcal_url, links.ics_url)


def abandon_bigchat(
    event: ReactionEvent, slack: SlackGateway, runtime: Runtime
) -> bool:
    settings = runtime.settings
    if (
        event.kind != "reaction_removed"
        or event.reaction != settings.JOIN_BIGCHAT_EMOJI
    ):
        return False
    found = _bigchat_thread(event, slack)
    if found is None:
        return False
    worksheet_id, _ = found

    def cancel() -> bool:
        status = cancel_registration(
            event.user, worksheet_id, runtime.members(), runtime.sheets()
        )
        if status is not CancellationStatus.CANCELLED:
            slack.send_thread_message(
                event.channel, event.ts, cancellation_notice(status, event.user)
            )
            return False
        slack.send_ephemeral(
            event.channel, event.user, cancelled_message(event.user), ts=event.ts
        )
        return True

    return with_loading_emoji(slack, event.channel, event.ts, cancel)


# --- 생성 (멘션 / 모달) ----------------------------------------------------------


def create_from_mention(
    command: CreateBigchat, event: MentionEvent, slack: SlackGateway, runtime: Runtime
) -> bool:
    parsed = CreateBigchatCommand.parse(command.sheet_name)
    if parsed is None:
        slack.send_ephemeral(
            event.channel,
            event.user,
            invalid_bigchat_name_message(event.user),
            ts=event.ts,
        )
        return False
    created = create_bigchat(parsed, runtime.sheets())
    slack.send_thread_message(
        event.channel,
        event.ts,
        bigchat_created_message(created.sheet_url, created.sheet_name),
    )
    # 모집글(스레드 부모). 스레드 없이 채널에 바로 멘션했다면 멘션 글 자체가 모집글이다.
    backfill_early_reactions(created, event.channel, event.root_ts, slack, runtime)
    return True


def backfill_early_reactions(
    created: BigchatCreated,
    channel: str,
    thread_ts: str,
    slack: SlackGateway,
    runtime: Runtime,
) -> None:
    """시트 게시 뒤, 시트가 생기기 전에 미리 달린 참여 반응을 등록한다. 오류는 스레드 경고로 알린다."""
    target_emoji = runtime.settings.JOIN_BIGCHAT_EMOJI
    reaction = slack.get_reaction(channel, thread_ts, target_emoji)
    if reaction is None:
        return

    try:
        registered = []
        for user in reaction.users:
            registration = register_applicant(
                user, created.worksheet_id, runtime.members(), runtime.sheets()
            )
            if registration.status is RegistrationStatus.REGISTERED:
                registered.append((user, registration.member))
            elif registration.status in (
                RegistrationStatus.MEMBER_NOT_FOUND,
                RegistrationStatus.MEMBER_LACKS_INFO,
            ):
                slack.send_thread_message(
                    channel, thread_ts, registration_notice(registration.status, user)
                )

        if not registered:
            return

        slack.send_thread_message(
            channel,
            thread_ts,
            early_reactions_registered_message(
                [u for u, _ in registered], target_emoji
            ),
        )
        for user, member in registered:
            try:
                slack.send_ephemeral(
                    channel,
                    user,
                    build_registration_info_message(user, member),
                    ts=thread_ts,
                )
            except SlackApiError as ex:
                # 슬랙 API 오류로 안내하지 못해도 다음 사용자로 진행한다.
                logger.warning(f"Failed to send registration info to {user}: {ex}")
    except Exception:
        logger.exception("Failed to backfill early reactions")
        slack.send_thread_message(
            channel, thread_ts, early_reactions_failed_message(target_emoji)
        )


def open_create_bigchat_modal(payload: ShortcutPayload, slack: SlackGateway) -> bool:
    slack.open_view(
        payload.trigger_id,
        create_bigchat_view(payload.channel, payload.thread_ts, payload.response_url),
    )
    return True


def submit_create_bigchat_modal(
    submission: ViewSubmission, ack, slack: SlackGateway, runtime: Runtime
) -> bool:
    values = submission.values
    name = (values[NAME_BLOCK][ACTION_ID]["value"] or "").strip()
    date = values[DATE_BLOCK][ACTION_ID]["selected_date"]  # YYYY-MM-DD
    start = values[START_BLOCK][ACTION_ID]["selected_time"]  # HH:mm
    end = values[END_BLOCK][ACTION_ID]["selected_time"]  # HH:mm

    errors = {}
    if not name:
        errors[NAME_BLOCK] = "이름을 입력해줘!"
    if end <= start:
        errors[END_BLOCK] = "종료 시각은 시작 시각보다 늦어야 해!"
    if errors:
        ack(response_action="errors", errors=errors)
        return False

    parsed = CreateBigchatCommand.parse(f"{name} {date[2:]} {start}~{end}")
    if parsed is None:
        ack(
            response_action="errors",
            errors={NAME_BLOCK: "형식이 올바르지 않아. 입력값을 다시 확인해줘!"},
        )
        return False

    ack()  # 3초 안에 응답하도록 시트 생성 전에 모달을 닫는다.
    created = create_bigchat(parsed, runtime.sheets())
    try:
        slack.send_thread_message(
            submission.channel,
            submission.thread_ts,
            bigchat_created_message(created.sheet_url, created.sheet_name),
        )
    except SlackApiError as ex:
        if ex.response["error"] not in ("not_in_channel", "channel_not_found"):
            raise
        # 채널 밖에서는 반응을 읽지 못해 일괄 등록을 건너뛰고 response_url 로 요청자에게 안내한다.
        slack.send_response_url_message(
            submission.response_url,
            bot_not_in_channel_message(created.sheet_url, created.sheet_name),
        )
        return True
    backfill_early_reactions(
        created, submission.channel, submission.thread_ts, slack, runtime
    )
    return True


# --- 수동 리마인더 (멘션) ---------------------------------------------------------


def remind_now(
    command: Reminder, event: MentionEvent, slack: SlackGateway, runtime: Runtime
) -> bool:
    def reply(text: str):
        slack.send_ephemeral(event.channel, event.user, text, ts=event.ts)

    if command.mode == "usage":
        reply(USAGE)
        return False
    if command.mode == "test" and not command.target_ids:
        reply(missing_targets_message(event.user))
        return False

    service = RemindBigchat(slack, runtime.sheets(), runtime.members())
    if command.mode == "broadcast":
        logger.warning(
            "Manual reminder BROADCAST triggered by %s — sending to every applicant",
            event.user,
        )
        result = service.run()
        reply(build_report(result, targets=None))
        return True

    targets = list(command.target_ids)
    logger.info("Manual reminder test triggered by %s, targets=%s", event.user, targets)
    result = service.run(only_user_ids=targets)
    reply(build_report(result, targets))
    return True


# --- Bolt 등록 ---------------------------------------------------------------------


def register(app, runtime: Runtime):
    admin = runtime.settings.ADMIN_CHANNEL

    @app.event("reaction_added")
    def handle_reaction_added_event(ack, event, client):
        ack()
        slack = runtime.slack_client(client)
        try:
            join_bigchat(ReactionEvent.from_payload(event), slack, runtime)
        except Exception as exc:
            report_failure(slack, admin, event, exc)

    @app.event("reaction_removed")
    def handle_reaction_removed_event(ack, event, client):
        ack()
        slack = runtime.slack_client(client)
        try:
            abandon_bigchat(ReactionEvent.from_payload(event), slack, runtime)
        except Exception as exc:
            report_failure(slack, admin, event, exc)

    @app.action(re.compile("calendar_.*"))
    def handle_calendar_button(ack):
        # 링크 버튼은 URL을 여는 것 외에 서버 동작이 없지만, ack하지 않으면 버튼에 ⚠️가 표시된다
        ack()

    @app.shortcut(CREATE_BIGCHAT_SHORTCUT_ID)
    def handle_create_bigchat_shortcut(ack, body, client):
        ack()
        slack = runtime.slack_client(client)
        try:
            open_create_bigchat_modal(ShortcutPayload.from_payload(body), slack)
        except Exception as exc:
            report_failure(slack, admin, body, exc)

    @app.view(CREATE_BIGCHAT_VIEW_ID)
    def handle_create_bigchat_view_submission(ack, body, client):
        # ack는 검증 결과(인라인 에러 vs 모달 닫기)에 따라 핸들러 안에서 호출된다
        slack = runtime.slack_client(client)
        try:
            submit_create_bigchat_modal(
                ViewSubmission.from_payload(body), ack, slack, runtime
            )
        except Exception as exc:
            report_failure(slack, admin, body, exc)
