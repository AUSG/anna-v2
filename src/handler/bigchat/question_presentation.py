"""Render QA answers and cited sources without external I/O."""

import re
from collections import Counter
from datetime import datetime, timezone
from typing import List, Tuple
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from implementation.qa_client import ChatResult

# Permit balanced parentheses inside a Markdown URL (for example Wikipedia
# paths) while keeping the final parenthesis as Markdown syntax.
_URL_WITH_BALANCED_PARENS = r"https?://(?:[^()\s<>|`]+|\([^()\s<>|`]*\))+"
_ANSWER_MARKDOWN_LINK = re.compile(
    rf"\[([^\]]+)\]\(({_URL_WITH_BALANCED_PARENS})\)", re.IGNORECASE
)
_ANSWER_SLACK_LINK = re.compile(r"<(https?://[^>|\s]+)(?:\|([^>]*))?>", re.IGNORECASE)
_ANSWER_MALFORMED_SLACK_LINK = re.compile(
    r"<(https?://[^>|\s]+)(?:\|([^>\n]*))?", re.IGNORECASE
)
# Backticks are delimiters rather than part of a URL.  Keep closing
# parentheses in the candidate so URLs such as ``/wiki/Foo_(bar)`` can be
# balanced by the normalizer below.
_ANSWER_PLAIN_URL = re.compile(r"(?:https?://|www\.)[^\s<>|`]+", re.IGNORECASE)
_TRAILING_HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]+$")
UNTRUSTED_LINK_MARKER = "[확인되지 않은 링크 제거]"


def render_parts(result) -> Tuple[str, List[str]]:
    """Return the cleaned answer and its Slack-formatted cited source links.

    The old answer-only return value is still accepted.
    """
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
    cited_ids = {citation for citation in result.citations if isinstance(citation, str)}
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
            # This is a synthetic source.  It has no external permalink.
            cited_sources.append(label)
    # The model sees source URLs in its context and may copy or invent links
    # in ``answer``.  Only links belonging to a cited source are trusted;
    # source links are rendered below from structured metadata.
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
    """Only put ordinary web URLs into Slack's angle-bracket link syntax."""
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
    """Keep only evidence-backed URLs copied into the generated answer.

    Citation links are appended from ``sources`` separately.  This prevents a
    malformed or hallucinated URL in the free-form model answer from becoming
    a clickable Slack link, while retaining a URL when it exactly matches a
    source the model cited.
    """

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
    # A missing closing ``>`` is not a valid Slack link, but leaving it in the
    # message still lets Slack interpret the URL unpredictably.
    answer = _ANSWER_MALFORMED_SLACK_LINK.sub(
        lambda match: match.group(0)
        if match.group(1) in allowed_urls
        else (match.group(2) or "") + UNTRUSTED_LINK_MARKER,
        answer,
    )
    answer = _ANSWER_MARKDOWN_LINK.sub(markdown_link, answer)
    return _ANSWER_PLAIN_URL.sub(plain_url, answer)


def _normalize_answer_url(candidate: str) -> str:
    """Remove sentence punctuation and unmatched closing URL delimiters.

    Korean text glued to a URL (``[링크](https://a.test/)은``) is a particle, not
    part of the URL, so it is dropped before the delimiter check.
    """
    trimmed = _TRAILING_HANGUL.sub("", candidate).rstrip(".,!?;:")
    while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
        trimmed = trimmed[:-1]
    return trimmed


def _format_timestamp(value: str) -> str:
    """Render ISO/Slack timestamps as a compact KST time, preserving bad input."""
    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    except (TypeError, ValueError, OverflowError):
        return value
