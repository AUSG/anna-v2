from typing import Union


def get_prop(obj, *keys: str) -> Union[str, None]:
    _obj = obj
    try:
        for key in keys:
            _obj = _obj[key]
    except (KeyError, TypeError):
        return None
    return _obj
