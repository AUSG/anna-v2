def search_value(d, key):
    """중첩 이벤트에서 주어진 키의 첫 값을 찾는다."""

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
