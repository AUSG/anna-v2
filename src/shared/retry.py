import time
from typing import Callable, Tuple, Type, TypeVar

T = TypeVar("T")


def retry(
    operation: Callable[[], T],
    *,
    attempts: int = 10,
    wait_sec: float = 3,
    non_retryable: Tuple[Type[BaseException], ...] = (),
) -> T:
    """non_retryable 은 즉시 전파하고 나머지는 고정 간격으로 재시도한다."""
    last_exception = None
    for _ in range(attempts):
        try:
            return operation()
        except non_retryable:
            raise
        except Exception as ex:
            last_exception = ex
            time.sleep(wait_sec)
    raise last_exception
