"""QA 답변과 인용 출처를 슬랙 형식으로 만든다."""

import re
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from features.questions.models import ChatResult

# URL 안의 한 겹 괄호를 허용한다.
_URL_WITH_BALANCED_PARENS = r"https?://(?:[^()\s<>|`]+|\([^()\s<>|`]*\))+"
_ANSWER_MARKDOWN_LINK = re.compile(
    rf"\[([^\]]+)\]\(({_URL_WITH_BALANCED_PARENS})\)", re.IGNORECASE
)
_ANSWER_SLACK_LINK = re.compile(r"<(https?://[^>|\s]+)(?:\|([^>]*))?>", re.IGNORECASE)
_ANSWER_MALFORMED_SLACK_LINK = re.compile(
    r"<(https?://[^>|\s]+)(?:\|([^>\n]*))?", re.IGNORECASE
)
# 백틱은 제외하고 남는 닫는 괄호는 아래에서 정리한다.
_ANSWER_PLAIN_URL = re.compile(r"(?:https?://|www\.)[^\s<>|`]+", re.IGNORECASE)
_TRAILING_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]+$")
UNTRUSTED_LINK_MARKER = "[확인되지 않은 링크 제거]"


def render_parts(result) -> tuple[str, list[str]]:
    """답변과 인용 출처 링크를 만든다. 구형 문자열 응답도 받는다."""
    if result is None:
        return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.", []
    if isinstance(result, str):
        return _strip_untrusted_answer_links(result, set()), []
    if not isinstance(result, ChatResult):
        return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.", []

    if result.answer:
        answer = result.answer
    elif result.status == "insufficient_evidence":
        answer = "흐음~ 관련 기록에서는 확인하지 못했어요."
    elif result.status == "conflicting_evidence":
        answer = "흐음~ 기록이 서로 달라서 확답하기 어렵네요."
    else:
        answer = "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"
    cited_ids = set(result.citations)
    source_counts = Counter(source.document_id for source in result.sources)
    unique_cited_sources = [
        source
        for source in result.sources
        if source.document_id in cited_ids and source_counts[source.document_id] == 1
    ]
    cited_sources = []
    for source in unique_cited_sources:
        url = _safe_source_url(source.url)
        label = _escape_slack_text(source.title or source.document_id)
        if source.timestamp:
            label = f"{label} · {_format_timestamp(source.timestamp)}"
        if url:
            cited_sources.append(f"<{url}|{label}>")
        elif (
            source.document_id == "conversation:current"
            and source.url == "conversation:current"
        ):
            # 현재 대화 출처에는 외부 링크가 없다.
            cited_sources.append(label)
    # 인용된 고유 출처의 URL과 근거 URL만 답변에 허용한다.
    allowed_answer_urls = {
        _safe_source_url(source.url) for source in unique_cited_sources
    }
    for source in unique_cited_sources:
        allowed_answer_urls.update(
            url
            for url in (
                _safe_source_url(candidate) for candidate in source.evidence_urls
            )
            if url
        )
    return _strip_untrusted_answer_links(answer, allowed_answer_urls), cited_sources


def _safe_source_url(url: str) -> str:
    """스킴과 구분자를 검사해 출처 URL을 고른다."""
    if (
        not isinstance(url, str)
        or any(char in url for char in "<>|`")
        or any(char.isspace() for char in url)
    ):
        return ""
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _escape_slack_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _strip_untrusted_answer_links(answer: str, allowed_urls: set[str]) -> str:
    """답변에서 찾은 URL을 인용 출처의 허용 목록과 대조한다."""

    def slack_link(match):
        url, label = match.group(1), match.group(2)
        return (
            match.group(0)
            if url in allowed_urls
            else (label or "") + UNTRUSTED_LINK_MARKER
        )

    def markdown_link(match):
        return (
            match.group(0)
            if match.group(2) in allowed_urls
            else match.group(1) + UNTRUSTED_LINK_MARKER
        )

    def plain_url(match):
        candidate = match.group(0)
        trimmed = _normalize_answer_url(candidate)
        suffix = candidate[len(trimmed) :]
        if trimmed in allowed_urls:
            return trimmed + suffix
        return UNTRUSTED_LINK_MARKER + suffix

    answer = _ANSWER_SLACK_LINK.sub(slack_link, answer)
    # 닫는 꺾쇠가 빠진 링크도 허용 목록으로 검사한다.
    answer = _ANSWER_MALFORMED_SLACK_LINK.sub(
        lambda match: (
            match.group(0)
            if match.group(1) in allowed_urls
            else (match.group(2) or "") + UNTRUSTED_LINK_MARKER
        ),
        answer,
    )
    answer = _ANSWER_MARKDOWN_LINK.sub(markdown_link, answer)
    return _ANSWER_PLAIN_URL.sub(plain_url, answer)


def _normalize_answer_url(candidate: str) -> str:
    """끝 한글, 문장부호, 남는 닫는 괄호 순으로 정리한다."""
    trimmed = _TRAILING_HANGUL.sub("", candidate).rstrip(".,!?;:")
    while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
        trimmed = trimmed[:-1]
    return trimmed


def _format_timestamp(value: str) -> str:
    """시각을 KST로 표시하며 형식이나 범위 오류면 원문을 남긴다."""
    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            parsed = datetime.fromtimestamp(float(value), tz=UTC)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except TypeError, ValueError, OverflowError:
        return value
