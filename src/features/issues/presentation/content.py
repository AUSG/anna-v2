"""GitHub 이슈에 표시할 본문과 출처."""


def build_issue_body(body: str, thread_context: str, footer: str) -> str:
    parts = []
    if body:
        parts.append(body)
    if thread_context:
        parts.append(f"### 슬랙 스레드\n\n{thread_context}")
    parts.append(footer)
    return "\n\n".join(parts)


def build_issue_footer(user: str | None, permalink: str) -> str:
    lines = ["---", f"슬랙에서 `{user}` 가 안나에게 요청해서 만들어진 이슈야."]
    if permalink:
        lines.append(f"원문: {permalink}")
    return "\n".join(lines)
