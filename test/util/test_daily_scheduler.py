import unittest
from datetime import datetime

from dateutil.tz import gettz

from util.daily_scheduler import next_fire_time

KST = gettz("Asia/Seoul")


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
