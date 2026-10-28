"""메서드 결과를 일정 시간 동안 캐시하는 데코레이터."""

import functools
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Concatenate


def ttl_cache[S, **P, R](
    *, maxsize: int, ttl: float, timer: Callable[[], float] = time.monotonic
) -> Callable[[Callable[Concatenate[S, P], R]], Callable[Concatenate[S, P], R]]:
    """최근에 사용한 결과를 최대 maxsize개까지 ttl초 동안 보관한다. 예외는 캐시하지 않는다.

    계산은 lock 안에서 실행하므로, 같은 요청이 동시에 들어와도 한 번만 계산한다.
    """

    def decorator(
        method: Callable[Concatenate[S, P], R],
    ) -> Callable[Concatenate[S, P], R]:
        entries: OrderedDict[Hashable, tuple[float, R]] = OrderedDict()
        lock = threading.RLock()

        @functools.wraps(method)
        def wrapper(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
            key = (self, args, tuple(sorted(kwargs.items())))
            with lock:
                entry = entries.get(key)
                if entry is not None and timer() < entry[0]:
                    entries.move_to_end(key)
                    return entry[1]
                value = method(self, *args, **kwargs)
                entries[key] = (timer() + ttl, value)
                entries.move_to_end(key)
                if len(entries) > maxsize:
                    entries.popitem(last=False)
                return value

        return wrapper

    return decorator
