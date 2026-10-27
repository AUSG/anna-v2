def strip_multiline(text, *args, ignore_first_line=True):
    """여러 줄 문자열의 공통 들여쓰기를 제거하고 {}를 인자 순서대로 치환한다."""
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
