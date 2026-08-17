import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 오래 자는 동안 시계가 조정(NTP 등)되어도 이 간격 안에 남은 시간을 다시 계산한다
_MAX_SLEEP_SEC = 5 * 60


def next_fire_time(now: datetime, hour: int, minute: int) -> datetime:
    """now 이후(정확히 now 인 시각은 제외) 가장 가까운 hour:minute 시각."""
    fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if fire_at <= now:
        fire_at += timedelta(days=1)
    return fire_at


class DailyScheduler(threading.Thread):
    """매일 tz 기준 hour:minute 에 job 을 실행하는 데몬 스레드.

    gunicorn 이 워커 1개로 뜨는 구성이라 (Makefile, .meta/deploy/Dockerfile)
    프로세스당 스레드 하나면 같은 날 중복 실행이 없다. 워커를 늘리려면
    이 스케줄러를 별도 프로세스로 분리해야 한다.
    """

    def __init__(self, job, hour: int, minute: int, tz, name: str = "daily-scheduler"):
        super().__init__(name=name, daemon=True)
        self.job = job
        self.hour = hour
        self.minute = minute
        self.tz = tz

    def run(self):
        while True:
            fire_at = next_fire_time(datetime.now(self.tz), self.hour, self.minute)
            self._sleep_until(fire_at)
            try:
                self.job()
            except Exception:
                logger.exception("Daily job failed: %s", self.name)

    def _sleep_until(self, fire_at: datetime):
        while True:
            remaining = (fire_at - datetime.now(self.tz)).total_seconds()
            if remaining <= 0:
                return
            time.sleep(min(remaining, _MAX_SLEEP_SEC))
