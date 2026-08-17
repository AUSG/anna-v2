import logging
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 오래 자는 동안 시계가 조정(NTP 등)되어도 이 간격 안에 남은 시간을 다시 계산한다
_MAX_SLEEP_SEC = 5 * 60

# 발사를 기다리는 동안 "스레드가 아직 살아있다"를 INFO 로 남기는 주기.
# 발사 시각에 로그가 아무것도 없을 때, 잡이 조용히 끝난 건지 프로세스가 죽어있던 건지
# 이 하트비트의 유무로 구분할 수 있다.
_HEARTBEAT_SEC = 60 * 60


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
            now = datetime.now(self.tz)
            fire_at = next_fire_time(now, self.hour, self.minute)
            logger.info(
                "[%s] next fire at %s (= %s UTC), in %s",
                self.name,
                fire_at.isoformat(timespec="seconds"),
                fire_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                _fmt_duration((fire_at - now).total_seconds()),
            )
            self._sleep_until(fire_at)

            logger.info(
                "[%s] firing job (scheduled=%s, now=%s)",
                self.name,
                fire_at.isoformat(timespec="seconds"),
                datetime.now(self.tz).isoformat(timespec="seconds"),
            )
            started_at = time.monotonic()
            try:
                self.job()
            except Exception:
                logger.exception("[%s] daily job failed", self.name)
            finally:
                logger.info(
                    "[%s] job returned after %.1fs",
                    self.name,
                    time.monotonic() - started_at,
                )

    def _sleep_until(self, fire_at: datetime):
        last_heartbeat = time.monotonic()
        while True:
            remaining = (fire_at - datetime.now(self.tz)).total_seconds()
            if remaining <= 0:
                return
            if time.monotonic() - last_heartbeat >= _HEARTBEAT_SEC:
                logger.info(
                    "[%s] waiting, %s until next fire",
                    self.name,
                    _fmt_duration(remaining),
                )
                last_heartbeat = time.monotonic()
            time.sleep(min(remaining, _MAX_SLEEP_SEC))


def _fmt_duration(seconds: float) -> str:
    total = int(max(seconds, 0))
    return f"{total // 3600}h {total % 3600 // 60}m {total % 60}s"
