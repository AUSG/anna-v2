import unittest
from unittest.mock import MagicMock

from handler.bigchat import CreateBigchatSheet, SimpleResponse, AttendBigchat, AbandonBigchat
from implementation.member_finder import Member
from implementation.slack_client import Message


def _sample_app_mention_event(msg):
    return {
        'client_msg_id': '8fb50d48-f93d-4cca-b9ca-6965479e9a93',
        'type': 'app_mention',
        'text': msg,
        'user': 'UQJ8HQJG5',
        'ts': '1689403771.805849',
        'blocks': [],  # not used and too long, so skipped
        'team': 'TQLEG4B38',
        'thread_ts': '1689403100.222939',
        'parent_user_id': 'UQJ8HQJG5',
        'channel': 'C03SZTDEDK3',
        'event_ts': '1689403771.805849'
    }


def _sample_reaction_added_event(emoji_name):
    return {
        'type': 'reaction_added',
        'user': 'UQJ8HQJG5',
        'reaction': emoji_name,
        'item': {
            'type': 'message',
            'channel': 'C03SZTDEDK3',
            'ts': '1688801145.307229'
        },
        'item_user': "U01BN035Y6L",
        'event_ts': '1688833113.003600'
    }


def _sample_reaction_removed_event(emoji_name):
    return {
        'type': 'reaction_removed',
        'user': 'UQJ8HQJG5',
        'reaction': emoji_name,
        'item': {
            'type': 'message',
            'channel': 'C03SZTDEDK3',
            'ts': '1688801145.307229'
        },
        'item_user': "U01BN035Y6L",
        'event_ts': '1688833113.003600'
    }


class TestCreateBigchatSheet(unittest.TestCase):
    def test_run(self):
        event = _sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.create_bigchat_sheet.assert_called_once()
        mock_gs_client.get_url.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert "새로운 빅챗, 등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]

    def test_not_run_by_command_notfound(self):
        event = _sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_not_run_by_sheet_name_notfound(self):
        event = _sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.assert_not_called()
        mock_slack_client.send_message.assert_called_once()
        assert result is False
        assert "시트 이름이 입력되지 않았어. 다시 입력해줘!" in mock_slack_client.send_message.call_args.kwargs["msg"]


class TestSimpleResponse(unittest.TestCase):
    def test_run(self):
        event = _sample_app_mention_event("<@U01BN035Y6L>")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.run()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] == "?"

    def test_not_run_by_text_not_empty(self):
        event = _sample_app_mention_event("<@U01BN035Y6L> 안녕?")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.run()

        mock_slack_client.send_message.assert_not_called()
        assert result is False


class TestAttendBigchat(unittest.TestCase):
    def test_run(self):
        event = _sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [Message(ts=event["item"]["ts"],
                                                              thread_ts="1689429129.825319",
                                                              channel="C03SZTDEDK3",
                                                              user="U01BN035Y6L",
                                                              text="새로운 빅챗을 모집합니다!"),
                                                      Message(ts=event["item"]["ts"],
                                                              thread_ts="1689429129.825319",
                                                              channel="C03SZTDEDK3",
                                                              user="U01BN035Y6L",
                                                              text="새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>")]
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="kor_name",
            eng_name="eng_name",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        sut = AttendBigchat(event, "U01BN035Y6L", "gogo", mock_slack_client, mock_member_manager)

        result = sut.run()

        mock_slack_client.get_replies.assert_called_once()
        mock_member_manager.find.assert_called_once()
        mock_member_manager.add_member_to_bigchat_worksheet.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert "등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]
        mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        assert "네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!" in \
               mock_slack_client.send_message_only_visible_to_user.call_args.kwargs["msg"]
        assert result is True


class TestAbandonBigchat(unittest.TestCase):
    def test_run(self):
        event = _sample_reaction_removed_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [Message(ts=event["item"]["ts"],
                                                              thread_ts="1689429129.825319",
                                                              channel="C03SZTDEDK3",
                                                              user="U01BN035Y6L",
                                                              text="새로운 빅챗을 모집합니다!"),
                                                      Message(ts=event["item"]["ts"],
                                                              thread_ts="1689429129.825319",
                                                              channel="C03SZTDEDK3",
                                                              user="U01BN035Y6L",
                                                              text="새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>")]
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="kor_name",
            eng_name="eng_name",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        mock_gs_client = MagicMock()
        sut = AbandonBigchat(event, "U01BN035Y6L", "gogo", mock_slack_client, mock_member_manager, mock_gs_client)

        result = sut.run()

        mock_slack_client.get_replies.assert_called_once()
        mock_member_manager.find.assert_called_once()
        mock_gs_client.delete_row.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert "등록을 취소했어." in mock_slack_client.send_message.call_args.kwargs["msg"]
