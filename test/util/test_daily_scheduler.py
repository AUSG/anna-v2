import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from util.bigchat_event import KST
from util.daily_scheduler import next_fire_time


class TestNextFireTime(unittest.TestCase):
    def test_before_fire_time_fires_today(self):
        now = datetime(2026, 8, 19, 8, 30, tzinfo=KST)

        assert next_fire_time(now, 20, 0) == datetime(2026, 8, 19, 20, 0, tzinfo=KST)

    def test_after_fire_time_fires_tomorrow(self):
        now = datetime(2026, 8, 19, 20, 0, 1, tzinfo=KST)

        assert next_fire_time(now, 20, 0) == datetime(2026, 8, 20, 20, 0, tzinfo=KST)

    def test_exactly_at_fire_time_fires_tomorrow(self):
        # job 실행 직후 다시 계산할 때 같은 시각에 한 번 더 돌지 않아야 한다
        now = datetime(2026, 8, 19, 20, 0, 0, tzinfo=KST)

        assert next_fire_time(now, 20, 0) == datetime(2026, 8, 20, 20, 0, tzinfo=KST)

    def test_crosses_month_boundary(self):
        now = datetime(2026, 8, 31, 23, 59, tzinfo=KST)

        assert next_fire_time(now, 20, 0) == datetime(2026, 9, 1, 20, 0, tzinfo=KST)


class TestFireTimeIsIndependentOfServerTimezone(unittest.TestCase):
    """서버가 어느 타임존에 있든 18:00 KST 라는 같은 절대 시각에 실행돼야 한다 (fly.io 머신은 UTC)."""

    def test_same_absolute_instant_under_any_server_timezone(self):
        original_tz = os.environ.get("TZ")
        try:
            for server_tz in ["UTC", "America/New_York", "Asia/Seoul"]:
                os.environ["TZ"] = server_tz
                time.tzset()

                fire_at = next_fire_time(datetime(2026, 8, 19, 8, 30, tzinfo=KST), 18, 0)

                assert fire_at.astimezone(timezone.utc) == datetime(
                    2026, 8, 19, 9, 0, tzinfo=timezone.utc
                ), server_tz  # 18:00 KST == 09:00 UTC
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_kst_is_resolvable_and_utc_plus_9(self):
        """gettz 가 None 을 주면 datetime.now(None) 이 서버 로컬 시각이 되어 발송 시각이 통째로 틀어진다."""
        assert KST is not None
        assert datetime(2026, 8, 19, 18, 0, tzinfo=KST).utcoffset() == timedelta(hours=9)
