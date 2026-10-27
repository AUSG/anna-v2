"""참여/취소 반응과 시트 게시 뒤 일괄 등록의 Slack 진입점."""

import unittest
from unittest.mock import call
from urllib.parse import parse_qs, urlsplit

from slack_sdk.errors import SlackApiError

from features.bigchat.models import (
    BigchatCreated,
    CancellationStatus,
    RegistrationStatus,
)
from features.bigchat.presentation.messages import (
    build_registration_info_message,
    cancellation_notice,
    cancelled_message,
    early_reactions_failed_message,
    early_reactions_registered_message,
    registered_message,
    registration_notice,
)
from features.bigchat.slack import (
    abandon_bigchat,
    backfill_early_reactions,
    join_bigchat,
)
from shared.gateways import AppendOutcome
from shared.slack_events import ReactionEvent
from shared.slack_models import Message, Reaction
from test.fixtures.runtime import fake_runtime, fake_settings
from test.fixtures.slack_events import (
    create_sample_member,
    create_sample_reaction_added_event,
    create_sample_reaction_removed_event,
)

WORKSHEET_ID = 161837744
SHEET_LINK_TEXT = (
    "새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/"
    "1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/"
    f"edit#gid={WORKSHEET_ID}|구글스프레드 시트>"
)
INTRO_TEXT = "이번 빅챗 소개글입니다"
PERMALINK = "https://ausg.slack.com/archives/C03SZTDEDK3/p1688801145307229"
NEW_FORMAT_TITLE = "AI 밋업 26-08-20 19:00~21:00"


def _message(ts, text):
    return Message(
        ts=ts,
        thread_ts="1689429129.825319",
        channel="C03SZTDEDK3",
        user="U01BN035Y6L",
        text=text,
    )


class ReactionTestBase(unittest.TestCase):
    def setUp(self):
        self.runtime = fake_runtime()
        self.slack = self.runtime.slack
        self.sheets = self.runtime.sheets()
        self.members = self.runtime.members()
        self.members.find.return_value = create_sample_member()
        self.sheets.append_row_if_absent.return_value = AppendOutcome.ADDED
        self.sheets.delete_row.return_value = True
        self.sheets.get_worksheet_title.return_value = NEW_FORMAT_TITLE
        self.slack.get_permalink.return_value = PERMALINK

    def _event(self, factory, emoji="gogo"):
        self.event_dict = factory(emoji)
        self.event = ReactionEvent.from_payload(self.event_dict)
        self.channel, self.ts, self.user = (
            self.event.channel,
            self.event.ts,
            self.event.user,
        )
        return self.event

    def _bigchat_thread(self, *, with_intro=True):
        """반응이 달린 글이 스레드 첫 글(모집글)이고 그 아래에 시트 링크 답글이 있다."""
        messages = [_message(self.ts, SHEET_LINK_TEXT)]
        if with_intro:
            messages = [
                _message(self.ts, INTRO_TEXT),
                _message(self.ts, SHEET_LINK_TEXT),
            ]
        self.slack.get_thread_of_message.return_value = messages

    def _call_names(self):
        return [name for name, _, _ in self.slack.mock_calls]

    def _assert_no_work(self):
        assert self.slack.add_reaction.mock_calls == []
        assert self.slack.remove_reaction.mock_calls == []
        assert self.slack.send_thread_message.mock_calls == []
        assert self.slack.send_ephemeral.mock_calls == []
        assert self.sheets.mock_calls == []
        assert self.members.mock_calls == []


class TestJoinBigchatFilters(ReactionTestBase):
    """관심 없는 이벤트는 Slack 을 읽지도, loading 이모지를 붙이지도 않는다."""

    def test_ignores_reaction_removed(self):
        event = self._event(create_sample_reaction_removed_event)

        assert join_bigchat(event, self.slack, self.runtime) is False

        assert self.slack.mock_calls == []
        self._assert_no_work()

    def test_ignores_other_emoji(self):
        event = self._event(create_sample_reaction_added_event, "thinking")

        assert join_bigchat(event, self.slack, self.runtime) is False

        assert self.slack.mock_calls == []
        self._assert_no_work()

    def test_reaction_on_a_reply_is_not_a_bigchat(self):
        event = self._event(create_sample_reaction_added_event)
        self.slack.get_thread_of_message.return_value = [
            _message("1688801100.000000", SHEET_LINK_TEXT)
        ]

        assert join_bigchat(event, self.slack, self.runtime) is False

        self.slack.get_thread_of_message.assert_called_once_with(self.channel, self.ts)
        self._assert_no_work()

    def test_empty_thread_is_not_a_bigchat(self):
        event = self._event(create_sample_reaction_added_event)
        self.slack.get_thread_of_message.return_value = []

        assert join_bigchat(event, self.slack, self.runtime) is False

        self._assert_no_work()

    def test_message_without_sheet_link_is_not_a_bigchat(self):
        """빅챗 글이 아닌 아무 메시지에 이모지를 달아도 아무 동작이 없으므로 이모지를 붙이지 않는다."""
        event = self._event(create_sample_reaction_added_event)
        self.slack.get_thread_of_message.return_value = [_message(self.ts, "점심 뭐 먹지")]

        assert join_bigchat(event, self.slack, self.runtime) is False

        self.slack.get_thread_of_message.assert_called_once_with(self.channel, self.ts)
        self._assert_no_work()

    def test_zero_gid_stops_before_loading_or_storage(self):
        event = self._event(create_sample_reaction_added_event)
        self.slack.get_thread_of_message.return_value = [
            _message(self.ts, "https://docs.google.com/spreadsheets/d/a/edit#gid=0")
        ]

        assert join_bigchat(event, self.slack, self.runtime) is False

        self._assert_no_work()


class TestJoinBigchat(ReactionTestBase):
    def setUp(self):
        super().setUp()
        self._event(create_sample_reaction_added_event)
        self._bigchat_thread()

    def _run(self):
        return join_bigchat(self.event, self.slack, self.runtime)

    def test_registered(self):
        result = self._run()

        assert result is True
        self.members.find.assert_called_once_with(self.user)
        self.sheets.append_row_if_absent.assert_called_once_with(
            WORKSHEET_ID,
            [
                "김동주",
                "school_name_or_company_name",
                "email@example.com",
                "010-1234-5678",
            ],
        )
        self.slack.send_thread_message.assert_called_once_with(
            self.channel, self.ts, registered_message(self.user)
        )
        assert "등록 완료!" in self.slack.send_thread_message.call_args.args[2]

        self.slack.send_ephemeral.assert_called_once()
        args, kwargs = self.slack.send_ephemeral.call_args
        info = build_registration_info_message(self.user, create_sample_member())
        assert args == (self.channel, self.user, info)
        assert kwargs["ts"] == self.ts
        assert "네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!" in info
        assert kwargs["blocks"][0] == {
            "type": "section",
            "text": {"type": "mrkdwn", "text": info},
        }

    def test_loading_emoji_wraps_the_actual_registration(self):
        """시트 조회(no-op 판별)는 이모지 없이, 실제 등록은 이모지를 붙인 채로 진행한다."""
        assert self._run() is True

        self.slack.add_reaction.assert_called_once_with(
            self.channel, self.ts, "loading"
        )
        self.slack.remove_reaction.assert_called_once_with(
            self.channel, self.ts, "loading"
        )
        names = self._call_names()
        assert names.index("get_thread_of_message") < names.index("add_reaction")
        assert names.index("add_reaction") < names.index("send_thread_message")
        assert names.index("send_thread_message") < names.index("send_ephemeral")
        assert names.index("send_ephemeral") < names.index("remove_reaction")

    def test_loading_emoji_removed_even_when_registration_fails(self):
        self.members.find.side_effect = RuntimeError("스프레드시트 접속 실패")

        with self.assertRaises(RuntimeError):
            self._run()

        self.slack.add_reaction.assert_called_once()
        self.slack.remove_reaction.assert_called_once()
        self.slack.send_thread_message.assert_not_called()
        self.slack.send_ephemeral.assert_not_called()

    def test_already_registered_skips_duplicate(self):
        """시트 생성 직후의 일괄 등록과 동시에 처리됐거나 이벤트가 중복
        전달된 경우, 중복 행을 만들지 않고 이미 등록됐다고만 알려준다."""
        self.sheets.append_row_if_absent.return_value = AppendOutcome.ALREADY_PRESENT

        result = self._run()

        assert result is True
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            registration_notice(RegistrationStatus.ALREADY_REGISTERED, self.user),
        )
        assert "이미 등록되어 있어" in self.slack.send_thread_message.call_args.args[2]
        self.slack.send_ephemeral.assert_not_called()

    def test_deleted_sheet_notifies_user(self):
        """시트가 이미 삭제된 경우, 전용 안내 메시지를 보내고 False 를 반환한다."""
        self.sheets.append_row_if_absent.return_value = AppendOutcome.WORKSHEET_MISSING

        result = self._run()

        assert result is False
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            registration_notice(RegistrationStatus.WORKSHEET_MISSING, self.user),
        )
        assert (
            "이 빅챗의 신청 시트를 찾을 수 없어" in self.slack.send_thread_message.call_args.args[2]
        )
        self.slack.send_ephemeral.assert_not_called()

    def test_member_not_found_notifies_user(self):
        self.members.find.return_value = None

        result = self._run()

        assert result is False
        self.sheets.append_row_if_absent.assert_not_called()
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            registration_notice(RegistrationStatus.MEMBER_NOT_FOUND, self.user),
        )
        assert "네 정보를 찾지 못했어" in self.slack.send_thread_message.call_args.args[2]
        self.slack.send_ephemeral.assert_not_called()

    def test_member_lacking_info_notifies_user(self):
        self.members.find.return_value = create_sample_member(phone="phone")

        result = self._run()

        assert result is False
        self.sheets.append_row_if_absent.assert_not_called()
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            registration_notice(RegistrationStatus.MEMBER_LACKS_INFO, self.user),
        )
        assert "누락된 값이 있어" in self.slack.send_thread_message.call_args.args[2]
        self.slack.send_ephemeral.assert_not_called()


class TestJoinBigchatCalendarBlocks(ReactionTestBase):
    """등록 성공 뒤 안내에 실리는 캘린더 버튼."""

    def setUp(self):
        super().setUp()
        self._event(create_sample_reaction_added_event)
        self._bigchat_thread()

    def _blocks(self):
        assert join_bigchat(self.event, self.slack, self.runtime) is True
        self.slack.send_ephemeral.assert_called_once()
        return self.slack.send_ephemeral.call_args.kwargs["blocks"]

    def _buttons(self):
        blocks = self._blocks()
        assert blocks is not None
        return blocks[1]["elements"]

    def test_new_format_sheet_with_secret_has_gcal_and_ics(self):
        buttons = self._buttons()

        assert [b["action_id"] for b in buttons] == ["calendar_gcal", "calendar_ics"]
        gcal_url, ics_url = buttons[0]["url"], buttons[1]["url"]
        # gcal은 직링크여야 한다 — 서버 302 경유 시 모바일 앱 링크 핸드오프가 끊긴다
        assert gcal_url.startswith("https://calendar.google.com/calendar/render?")
        # gcal 본문은 permalink가 맨 앞, 그 아래 소개글(스레드 첫 글) — 잘려도 permalink는 항상 남는다
        details = parse_qs(urlsplit(gcal_url).query)["details"][0]
        assert details == f"슬랙에서 소개글 보기: {PERMALINK}\n\n{INTRO_TEXT}"
        assert ics_url.startswith(
            f"https://anna.test/bigchat/{WORKSHEET_ID}/event.ics?"
        )
        query = parse_qs(urlsplit(ics_url).query)
        assert (
            query["channel"] == [self.channel]
            and query["ts"] == [self.ts]
            and "token" in query
        )
        self.sheets.get_worksheet_title.assert_called_once_with(WORKSHEET_ID)
        self.slack.get_permalink.assert_called_once_with(self.channel, self.ts)

    def test_without_secret_has_gcal_only(self):
        self.runtime.settings = fake_settings(ICS_TOKEN_SECRET="")
        self.slack.get_permalink.return_value = None

        buttons = self._buttons()

        assert [b["action_id"] for b in buttons] == ["calendar_gcal"]
        # permalink 실패 시 (잘린) 소개글로 폴백
        assert parse_qs(urlsplit(buttons[0]["url"]).query)["details"] == [INTRO_TEXT]

    def test_keeps_permalink_when_long_intro_truncated(self):
        self.slack.get_thread_of_message.return_value = [
            _message(self.ts, "긴 소개글 " * 2000),
            _message(self.ts, SHEET_LINK_TEXT),
        ]

        buttons = self._buttons()

        gcal_url = buttons[0]["url"]
        assert len(gcal_url) <= 2900
        assert "ausg.slack.com" in gcal_url  # 소개글이 잘려도 맨 앞의 permalink는 남는다

    def test_old_format_sheet_registers_without_buttons(self):
        """구형식 시트여도 참가 신청은 그대로 성공하고, 캘린더 버튼만 생략된다."""
        self.sheets.get_worksheet_title.return_value = "빅챗 23-07-31"

        assert self._blocks() is None

        self.sheets.append_row_if_absent.assert_called_once()
        self.slack.send_thread_message.assert_called_once_with(
            self.channel, self.ts, registered_message(self.user)
        )

    def test_missing_worksheet_title_registers_without_buttons(self):
        self.sheets.get_worksheet_title.return_value = None

        assert self._blocks() is None

    def test_title_lookup_failure_registers_without_buttons(self):
        """부가 조회 실패는 등록을 실패시키지 않는다."""
        self.sheets.get_worksheet_title.side_effect = RuntimeError("시트 조회 실패")

        assert self._blocks() is None

        self.sheets.append_row_if_absent.assert_called_once()
        self.slack.remove_reaction.assert_called_once()


class TestAbandonBigchat(ReactionTestBase):
    def setUp(self):
        super().setUp()
        self._event(create_sample_reaction_removed_event)
        self._bigchat_thread()

    def _run(self):
        return abandon_bigchat(self.event, self.slack, self.runtime)

    def test_ignores_reaction_added(self):
        self._event(create_sample_reaction_added_event)

        assert self._run() is False

        assert self.slack.mock_calls == []
        self._assert_no_work()

    def test_ignores_other_emoji(self):
        self._event(create_sample_reaction_removed_event, "thinking")

        assert self._run() is False

        assert self.slack.mock_calls == []
        self._assert_no_work()

    def test_reaction_on_a_reply_is_not_a_bigchat(self):
        self.slack.get_thread_of_message.return_value = [
            _message("1688801100.000000", SHEET_LINK_TEXT)
        ]

        assert self._run() is False

        self._assert_no_work()

    def test_message_without_sheet_link_is_not_a_bigchat(self):
        self.slack.get_thread_of_message.return_value = [_message(self.ts, "점심 뭐 먹지")]

        assert self._run() is False

        self.slack.get_thread_of_message.assert_called_once_with(self.channel, self.ts)
        self._assert_no_work()

    def test_zero_gid_stops_before_loading_or_storage(self):
        self.slack.get_thread_of_message.return_value = [
            _message(self.ts, "https://docs.google.com/spreadsheets/d/a/edit#gid=0")
        ]

        assert self._run() is False

        self._assert_no_work()

    def test_cancelled(self):
        result = self._run()

        assert result is True
        self.members.find.assert_called_once_with(self.user)
        self.sheets.delete_row.assert_called_once_with(
            WORKSHEET_ID, "email@example.com"
        )
        self.slack.send_ephemeral.assert_called_once_with(
            self.channel, self.user, cancelled_message(self.user), ts=self.ts
        )
        assert "등록을 취소했어." in self.slack.send_ephemeral.call_args.args[2]
        self.slack.send_thread_message.assert_not_called()

    def test_loading_emoji_wraps_the_actual_cancellation(self):
        assert self._run() is True

        self.slack.add_reaction.assert_called_once_with(
            self.channel, self.ts, "loading"
        )
        self.slack.remove_reaction.assert_called_once_with(
            self.channel, self.ts, "loading"
        )
        names = self._call_names()
        assert names.index("get_thread_of_message") < names.index("add_reaction")
        assert names.index("add_reaction") < names.index("send_ephemeral")
        assert names.index("send_ephemeral") < names.index("remove_reaction")

    def test_loading_emoji_removed_even_when_cancellation_fails(self):
        self.sheets.delete_row.side_effect = RuntimeError("스프레드시트 접속 실패")

        with self.assertRaises(RuntimeError):
            self._run()

        self.slack.add_reaction.assert_called_once()
        self.slack.remove_reaction.assert_called_once()

    def test_deleted_sheet_notifies_user(self):
        """시트가 이미 삭제된 경우, 전용 안내 메시지를 보내고 False 를 반환한다."""
        self.sheets.delete_row.return_value = False

        result = self._run()

        assert result is False
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            cancellation_notice(CancellationStatus.WORKSHEET_MISSING, self.user),
        )
        assert (
            "이 빅챗의 신청 시트를 찾을 수 없어서 등록을 취소하지 못했어"
            in self.slack.send_thread_message.call_args.args[2]
        )
        self.slack.send_ephemeral.assert_not_called()

    def test_member_not_found_notifies_user(self):
        self.members.find.return_value = None

        result = self._run()

        assert result is False
        self.sheets.delete_row.assert_not_called()
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            cancellation_notice(CancellationStatus.MEMBER_NOT_FOUND, self.user),
        )
        self.slack.send_ephemeral.assert_not_called()

    def test_member_lacking_info_notifies_user(self):
        self.members.find.return_value = create_sample_member(email="")

        result = self._run()

        assert result is False
        self.sheets.delete_row.assert_not_called()
        self.slack.send_thread_message.assert_called_once_with(
            self.channel,
            self.ts,
            cancellation_notice(CancellationStatus.MEMBER_LACKS_INFO, self.user),
        )
        self.slack.send_ephemeral.assert_not_called()


class TestBackfillEarlyReactions(unittest.TestCase):
    CHANNEL = "C03SZTDEDK3"
    THREAD_TS = "1689403100.222939"
    CREATED = BigchatCreated(
        worksheet_id=WORKSHEET_ID,
        sheet_name=NEW_FORMAT_TITLE,
        sheet_url=f"https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid={WORKSHEET_ID}",
    )

    def setUp(self):
        self.runtime = fake_runtime()
        self.slack = self.runtime.slack
        self.sheets = self.runtime.sheets()
        self.members = self.runtime.members()
        self.sheets.append_row_if_absent.return_value = AppendOutcome.ADDED
        self.member_by_user = {}
        self.members.find.side_effect = lambda user: self.member_by_user.get(user)

    def _reacted(self, *users):
        self.slack.get_reaction.return_value = Reaction(
            name="gogo", users=list(users), count=len(users)
        )

    def _member(self, user, **overrides):
        self.member_by_user[user] = create_sample_member(**overrides)
        return self.member_by_user[user]

    def _run(self):
        return backfill_early_reactions(
            self.CREATED, self.CHANNEL, self.THREAD_TS, self.slack, self.runtime
        )

    def _group_message(self, *users):
        return call.send_thread_message(
            self.CHANNEL,
            self.THREAD_TS,
            early_reactions_registered_message(list(users), "gogo"),
        )

    def _info(self, user):
        return call.send_ephemeral(
            self.CHANNEL,
            user,
            build_registration_info_message(user, self.member_by_user[user]),
            ts=self.THREAD_TS,
        )

    def test_no_reaction_does_nothing(self):
        self.slack.get_reaction.return_value = None

        assert self._run() is None

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo")
        ]
        assert self.sheets.mock_calls == []
        assert self.members.mock_calls == []

    def test_registers_everyone_who_reacted_early(self):
        self._reacted("U_A", "U_B")
        member_a, member_b = self._member("U_A", kor_name="가"), self._member(
            "U_B", kor_name="나"
        )

        self._run()

        assert self.sheets.append_row_if_absent.mock_calls == [
            call(WORKSHEET_ID, member_a.transform_for_spreadsheet()),
            call(WORKSHEET_ID, member_b.transform_for_spreadsheet()),
        ]
        # 전원 등록 뒤 한 번의 그룹 안내, 그다음 각자에게만 보이는 신청 정보
        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            self._group_message("U_A", "U_B"),
            self._info("U_A"),
            self._info("U_B"),
        ]
        group = self.slack.send_thread_message.call_args.args[2]
        assert group == "<@U_A> <@U_B> 시트가 만들어지기 전에 :gogo:를 눌러줬구나! 지금 등록 완료했어!"

    def test_incomplete_members_get_thread_notices(self):
        self._reacted("U_UNKNOWN", "U_PARTIAL", "U_OK")
        self._member("U_PARTIAL", phone="")
        self._member("U_OK")

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            call.send_thread_message(
                self.CHANNEL,
                self.THREAD_TS,
                registration_notice(RegistrationStatus.MEMBER_NOT_FOUND, "U_UNKNOWN"),
            ),
            call.send_thread_message(
                self.CHANNEL,
                self.THREAD_TS,
                registration_notice(RegistrationStatus.MEMBER_LACKS_INFO, "U_PARTIAL"),
            ),
            self._group_message("U_OK"),
            self._info("U_OK"),
        ]

    def test_already_registered_users_are_silently_skipped(self):
        """join_bigchat 과 동시에 처리된 사람은 그쪽에서 이미 안내를 받았다."""
        self._reacted("U_DUP", "U_OK")
        self._member("U_DUP")
        self._member("U_OK")
        self.sheets.append_row_if_absent.side_effect = [
            AppendOutcome.ALREADY_PRESENT,
            AppendOutcome.ADDED,
        ]

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            self._group_message("U_OK"),
            self._info("U_OK"),
        ]

    def test_nothing_is_announced_when_nobody_was_registered(self):
        self._reacted("U_DUP")
        self._member("U_DUP")
        self.sheets.append_row_if_absent.return_value = AppendOutcome.ALREADY_PRESENT

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo")
        ]

    def test_ephemeral_slack_error_continues_to_next_user(self):
        self._reacted("U_LEFT", "U_OK")
        self._member("U_LEFT")
        self._member("U_OK")
        self.slack.send_ephemeral.side_effect = [
            SlackApiError("boom", {"error": "user_not_in_channel"}),
            None,
        ]

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            self._group_message("U_LEFT", "U_OK"),
            self._info("U_LEFT"),
            self._info("U_OK"),
        ]

    def test_unexpected_ephemeral_error_stops_with_a_warning(self):
        self._reacted("U_LEFT", "U_OK")
        self._member("U_LEFT")
        self._member("U_OK")
        self.slack.send_ephemeral.side_effect = [RuntimeError("신청 정보 안내 실패"), None]

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            self._group_message("U_LEFT", "U_OK"),
            self._info("U_LEFT"),
            call.send_thread_message(
                self.CHANNEL, self.THREAD_TS, early_reactions_failed_message("gogo")
            ),
        ]

    def test_registration_error_stops_with_a_warning(self):
        self._reacted("U_A", "U_B")
        self._member("U_A")
        self._member("U_B")
        self.sheets.append_row_if_absent.side_effect = RuntimeError("스프레드시트 접속 실패")

        self._run()

        self.sheets.append_row_if_absent.assert_called_once()
        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            call.send_thread_message(
                self.CHANNEL, self.THREAD_TS, early_reactions_failed_message("gogo")
            ),
        ]
        assert (
            "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘"
            in self.slack.send_thread_message.call_args.args[2]
        )

    def test_group_message_error_stops_with_a_warning(self):
        self._reacted("U_A")
        self._member("U_A")
        self.slack.send_thread_message.side_effect = [RuntimeError("일괄 안내 실패"), None]

        self._run()

        assert self.slack.mock_calls == [
            call.get_reaction(self.CHANNEL, self.THREAD_TS, "gogo"),
            self._group_message("U_A"),
            call.send_thread_message(
                self.CHANNEL, self.THREAD_TS, early_reactions_failed_message("gogo")
            ),
        ]
        self.slack.send_ephemeral.assert_not_called()

    def test_reaction_read_error_propagates(self):
        """반응 조회 자체가 실패하면 경고 없이 호출자에게 올라간다 (오류 경계가 관리자에게 알린다)."""
        self.slack.get_reaction.side_effect = RuntimeError("반응 조회 실패")

        with self.assertRaisesRegex(RuntimeError, "반응 조회 실패"):
            self._run()

        self.slack.send_thread_message.assert_not_called()
        assert self.members.mock_calls == []
