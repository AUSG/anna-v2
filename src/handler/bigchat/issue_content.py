from handler.mention_router import (
    ISSUE_TRIGGER_PATTERN as TRIGGER_PAT,
    MENTION_PATTERN as MENTION_PAT,
)

# 슬랙 한 줄이 그대로 제목이 되므로, 깃허브 제한(256자)보다 짧게 잘라 목록에서 읽히게 한다
MAX_TITLE_LEN = 120


def parse_issue_command(text: str) -> tuple[str, str]:
    """트리거 뒤의 첫 줄을 제목으로, 나머지 줄을 본문으로 나눈다."""
    after_trigger = TRIGGER_PAT.split(text, maxsplit=1)[-1]
    # 안나 멘션이 명령 앞뒤 어디에 있든 제목에 섞이지 않게 걷어낸다
    cleaned = MENTION_PAT.sub("", after_trigger).strip()
    # "이슈 만들어줄래? 제목", "이슈 만들어줘: 제목" 처럼 어미 뒤에 남는 문장부호를 턴다
    cleaned = cleaned.lstrip("?!.,:;~ \t")
    if not cleaned:
        return "", ""

    title, _, body = cleaned.partition("\n")
    title = title.strip()
    if len(title) > MAX_TITLE_LEN:
        title = title[: MAX_TITLE_LEN - 1].rstrip() + "…"
    return title, body.strip()


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
