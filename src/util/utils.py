import functools
import time


def search_value(d, key):
    """
    주어진 key 에 해당하는 value 를 찾아주는 메서드.

    XXX: 자세한 용례는 테스트 코드를 참고할 것.
    """

    # noinspection PyShadowingNames
    def _search_value(d, key):
        for k, v in d.items():
            if k == key:
                yield v
            elif isinstance(v, dict):
                yield from _search_value(v, key)
            elif isinstance(v, list):
                for i in v:
                    if not isinstance(i, str):
                        yield from _search_value(i, key)

    try:
        return next(_search_value(d, key))
    except StopIteration:
        return None


def strip_multiline(text, *args, ignore_first_line=True):
    """
    XXX: python multiline 표기법(세 개의 쌍따옴표를 이용함)이 전체 코드 가독성을 떨어뜨려 이 유틸 함수를 만들게 되었음.

    :param args: '{}' 를 찾아 주어진 args 로 replace 한다
    """

    min_space_sz = 9999999999
    if ignore_first_line:
        lines = text.splitlines()[1:]
    else:
        lines = text.splitlines()
    for line in lines:
        min_space_sz = min(min_space_sz, len(line) - len(line.lstrip()))

    parts = []
    for line in lines:
        parts.append(line[min_space_sz:])

    result = "\n".join(parts)
    if args:
        for arg in args:
            result = result.replace("{}", arg, 1)

    return result


def with_retry(max_try_cnt=10, fixed_wait_time_in_sec=3):
    """
    usage: @retry(3, 1)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_try_cnt):
                try:
                    return func(*args, **kwargs)
                except Exception as ex:
                    last_exception = ex
                    time.sleep(fixed_wait_time_in_sec)
            raise last_exception

        return wrapper

    return decorator
