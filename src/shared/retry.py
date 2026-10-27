import functools
import time


def with_retry(max_try_cnt=10, fixed_wait_time_in_sec=3, non_retryable_exceptions=()):
    """non_retryable_exceptions는 즉시 전파하고 나머지는 고정 간격으로 재시도한다."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_try_cnt):
                try:
                    return func(*args, **kwargs)
                except non_retryable_exceptions:
                    raise
                except Exception as ex:
                    last_exception = ex
                    time.sleep(fixed_wait_time_in_sec)
            raise last_exception

        return wrapper

    return decorator
