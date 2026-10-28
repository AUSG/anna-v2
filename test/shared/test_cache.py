import threading
import time

import pytest

from shared.cache import ttl_cache


def make_service(maxsize=10, ttl=60, timer=time.monotonic, delay=0.0):
    """호출된 인자를 calls 에 남기는 캐시 메서드. key 가 "error" 면 예외를 던진다."""
    calls = []

    class Service:
        @ttl_cache(maxsize=maxsize, ttl=ttl, timer=timer)
        def get(self, key: str, suffix: str = "") -> str:
            calls.append(key + suffix)
            time.sleep(delay)
            if key == "error":
                raise KeyError(key)
            return key + suffix

    return Service, calls


def test_result_is_kept_until_ttl():
    now = [0.0]
    service, calls = make_service(ttl=60, timer=lambda: now[0])
    s = service()
    s.get("a")
    now[0] = 59.9
    s.get("a")
    now[0] = 60.0
    s.get("a")
    assert calls == ["a", "a"]


def test_least_recently_used_entry_is_evicted():
    service, calls = make_service(maxsize=2)
    s = service()
    for key in ["a", "b", "a", "c", "a", "b"]:
        s.get(key)
    assert calls == ["a", "b", "c", "b"]


def test_instance_and_arguments_are_part_of_key():
    service, calls = make_service()
    s1, s2 = service(), service()
    for s, kwargs in [(s1, {}), (s1, {}), (s1, {"suffix": "!"}), (s2, {})]:
        s.get("a", **kwargs)
    assert calls == ["a", "a!", "a"]


def test_exception_is_not_cached():
    service, calls = make_service()
    s = service()
    for _ in range(2):
        with pytest.raises(KeyError):
            s.get("error")
    assert calls == ["error", "error"]


def test_concurrent_same_request_computes_once():
    service, calls = make_service(delay=0.05)
    s = service()
    threads = [threading.Thread(target=s.get, args=("a",)) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == ["a"]
