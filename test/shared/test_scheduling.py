import os
import time
import unittest
from datetime import datetime, timedelta, timezone

from shared.time import KST
from shared.scheduling import next_fire_time, run_with_admin_alert
from test.fixtures.runtime import fake_slack


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

                fire_at = next_fire_time(
                    datetime(2026, 8, 19, 8, 30, tzinfo=KST), 18, 0
                )

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
        assert datetime(2026, 8, 19, 18, 0, tzinfo=KST).utcoffset() == timedelta(
            hours=9
        )


class TestRunWithAdminAlert(unittest.TestCase):
    def test_returns_job_result_without_touching_slack(self):
        slack = fake_slack()

        result = run_with_admin_alert(
            lambda: "digest posted",
            label="daily-digest",
            slack=slack,
            admin_channel="C_ADMIN",
        )

        assert result == "digest posted"
        slack.send_channel_message.assert_not_called()

    def test_swallows_job_failure_and_alerts_admin_with_traceback(self):
        slack = fake_slack()

        def job():
            raise RuntimeError("crawler down")

        result = run_with_admin_alert(
            job, label="daily-digest", slack=slack, admin_channel="C_ADMIN"
        )

        assert result is None  # 스케줄러 스레드가 죽지 않는다
        slack.send_channel_message.assert_called_once()
        channel, text = slack.send_channel_message.call_args.args
        assert channel == "C_ADMIN"
        assert "daily-digest" in text
        assert "RuntimeError: crawler down" in text
        assert "in job" in text  # traceback

    def test_notification_failure_is_swallowed_too(self):
        slack = fake_slack()
        slack.send_channel_message.side_effect = RuntimeError("slack down")

        def job():
            raise RuntimeError("crawler down")

        assert (
            run_with_admin_alert(
                job, label="daily-digest", slack=slack, admin_channel="C_ADMIN"
            )
            is None
        )
