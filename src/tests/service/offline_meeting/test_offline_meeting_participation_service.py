from tests.util import enable_dummy_envs

# TODO : 다음 조건 만족 시 제거
#  env 깡으로 박아둔 것 때문에 아래 파일들 import 시 env error 발생. env 불러오는 코드를 한 파일로 물리적으로 응집하고 테스트 환경을 위한 기본값 넣기
enable_dummy_envs()

from unittest import TestCase
from unittest.mock import Mock
from expiringdict import ExpiringDict

from service.offline_meeting.member import Member

from service.offline_meeting.offline_meeting_participation_service import OfflineMeetingParticipationService


class OfflineMeetingParticipationServiceTest(TestCase):
    def test_success_must_store_worksheet_id_to_cache_when_new_participate(self):
        """
        worksheet_id 가 cache에 기록된 적이 없고
        새로운 최초 참여 시도(is_new)라면, cache에 {worksheet_id: True}를 기록한다
        """
        # given
        mock_slack_client = Mock()
        mock_gs_client = Mock()

        mock_worksheet_maker = Mock()
        is_new = True
        worksheet_id = "worksheet_id"
        mock_worksheet_maker.find_or_create_worksheet.return_value = is_new, worksheet_id

        worksheet_id_cache = ExpiringDict(max_len=100, max_age_seconds=60 * 60)

        service = OfflineMeetingParticipationService(
            raw_event={"ts": "ts", "channel": "channel"}, action_commander=Mock(), slack_client=mock_slack_client,
            gs_client=mock_gs_client, member_finder=Mock(), worksheet_maker=mock_worksheet_maker,
            is_exist_worksheet_cache=worksheet_id_cache,
        )
        member = Member(email="email", kor_name="kor_name", eng_name="eng_name", phone="phone",
                        school_name_or_company_name="school_name_or_company_name")

        # when
        service._participate(member)

        # then
        assert worksheet_id_cache.get(worksheet_id) is True

    def test_success_must_create_worksheet_when_real_first_participation(self):
        """
        진짜 최초 요청에만 새로운 시트를 만들어야한다.
        cache에 이미 worksheet_id가 기록되어 있다면,
        slack API 딜레이로 인해 새로운 최초 참여 시도(is_new)로 판정되어도, 새로운 시트를 생성하지 않는다.
        """

        # given
        mock_slack_client = Mock()

        mock_gs_client = Mock()
        mock_gs_client.tell.return_value = None

        mock_worksheet_maker = Mock()
        is_new = True
        worksheet_id = "worksheet_id"
        mock_worksheet_maker.find_or_create_worksheet.return_value = is_new, worksheet_id

        worksheet_id_cache = ExpiringDict(max_len=100, max_age_seconds=60 * 60)
        worksheet_id_cache[worksheet_id] = True

        service = OfflineMeetingParticipationService(
            raw_event={"ts": "ts", "channel": "channel"}, action_commander=Mock(), slack_client=mock_slack_client,
            gs_client=mock_gs_client, member_finder=Mock(), worksheet_maker=mock_worksheet_maker,
            is_exist_worksheet_cache=worksheet_id_cache,
        )

        member = Member(email="email", kor_name="kor_name", eng_name="eng_name", phone="phone",
                        school_name_or_company_name="school_name_or_company_name")

        # when
        service._participate(member)

        # then
        # 한 번만 호출되어야함
        mock_slack_client.tell.assert_called_once_with(msg=f"<@{service.event.user}>, 등록 완료!", ts=service.event.ts)
