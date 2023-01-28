from tests.util import enable_dummy_envs

# TODO : 다음 조건 만족 시 제거
#  env 깡으로 박아둔 것 때문에 아래 파일들 import 시 env error 발생. env 불러오는 코드를 한 파일로 물리적으로 응집하고 테스트 환경을 위한 기본값 넣기
enable_dummy_envs()

import threading
import time
from unittest.mock import Mock

from implementation import GoogleSpreadsheetClient, SlackClient
from service.offline_meeting.member import Member
from service.offline_meeting.offline_meeting_participation_service import OfflineMeetingParticipationService
from service.offline_meeting.worksheet_finder import WorksheetMaker

from unittest import TestCase


class MockWorksheetMakerWithTimeSleep(WorksheetMaker):
    def __init__(self, slack_client: SlackClient, gs_client: GoogleSpreadsheetClient, time_for_sleep: int):
        super().__init__(slack_client, gs_client)
        self.time_for_sleep = time_for_sleep

    def find_or_create_worksheet(self, ts: str, channel: str, spreadsheet_id: str):
        time.sleep(self.time_for_sleep)


class OfflineMeetingParticipationServiceTest(TestCase):
    def test_success_participate_at_same_time_then_wait_until_other_participation_is_finished(self):
        """
        동시에 참여 요청 시 다른 참여 요청에 대한 task가 종료될 때까지 대기한다
        """
        channel_id = "channel_id"
        mock_slack_client: SlackClient = Mock()
        mock_gs_client: GoogleSpreadsheetClient = Mock()

        # 비동기적으로 시트를 생성하는 상황을 연출하기 위해 2초 sleep하게 함
        time_for_sleep = 2
        mock_worksheet_maker: WorksheetMaker = MockWorksheetMakerWithTimeSleep(
            slack_client=mock_slack_client,
            gs_client=mock_gs_client,
            time_for_sleep=time_for_sleep,
        )

        raw_event = {
            "item": {"ts": "ts", "channel": channel_id},
        }

        participate_single_lock: threading.Lock = threading.Lock()

        service = OfflineMeetingParticipationService(
            raw_event=raw_event, action_commander=Mock(), slack_client=mock_slack_client,
            gs_client=mock_gs_client, member_finder=Mock(), worksheet_maker=mock_worksheet_maker,
            participate_single_lock=participate_single_lock,
        )

        some_valid_member = Member(email="email", kor_name="kor_name", eng_name="eng_name", phone="phone",
                                   school_name_or_company_name="school_name_or_company_name")

        start_time = time.time()

        threads = []
        t1 = threading.Thread(target=service._participate, args=(some_valid_member,))
        t1.start()
        threads.append(t1)

        t2 = threading.Thread(target=service._participate, args=(some_valid_member,))
        t2.start()
        threads.append(t2)

        for t in threads:
            t.join()

        # 각 스레드가 작업을 마쳤을 때 위에서 MockWorksheetMakerWithTimeSleep에 설정한 timeout의 2배라면 thread lock 잘 되는 것으로 판단
        assert time_for_sleep * len(threads) <= time.time() - start_time
