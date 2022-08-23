from typing import Union, List


def get_prop(obj: object, *keys: str) -> Union[str, List[str], None]:
    _obj = obj
    try:
        for key in keys:
            _obj = _obj[key]
    except (KeyError, TypeError):
        return None
    return _obj
