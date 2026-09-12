# 다국어(한국어) 시스템 프롬프트 문자열이 길어, 이 파일은 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from handler.bigchat.mention_handler import MentionHandler
from implementation.qa_client import (
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_AUTHOR_CHARS,
    MAX_CONVERSATION_MESSAGE_CHARS,
    MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATION_TIMESTAMP_CHARS,
    ChatResult,
    QAClient,
)

logger = logging.getLogger(__name__)

# q) 이후의 질문을 추출하는 정규식
QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)
_ANSWER_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_ANSWER_SLACK_LINK = re.compile(r"<(https?://[^>|\s]+)(?:\|([^>]*))?>", re.IGNORECASE)
_ANSWER_MALFORMED_SLACK_LINK = re.compile(
    r"<(https?://[^>|\s]+)(?:\|([^>\n]*))?", re.IGNORECASE
)
_ANSWER_PLAIN_URL = re.compile(r"(?:https?://|www\.)[^\s<>|)]+", re.IGNORECASE)
UNTRUSTED_LINK_MARKER = "[확인되지 않은 링크 제거]"

DEFAULT_SYSTEM_PROMPT = """너는 AUSG(AWSKRUG University Student Group) 커뮤니티의 멤버 같은 AI, ANNA야.
딱딱한 봇이 아니라 센스 있고 유쾌한 커뮤니티 멤버 한 명처럼 답해.
함께 주어지는 '현재 진행 중인 대화'와 '과거 커뮤니티 대화 기록'을 근거로 답한다.

원칙:
- 기본은 한국어로 친근하고 위트 있게 답한다. 다만 한국어만 고집할 필요는 없어 — 영어로 물으면 영어로 답해도 되고, 기술 용어·고유명사는 원어 그대로 써도 된다. 단, 과하거나 억지 드립은 금물.
- 재미는 양념이고 정확도가 우선이다. 근거를 종합해 핵심을 먼저 짚고, 링크·일정 등 구체 정보는 정확히 옮긴다.
- '현재 진행 중인 대화'가 있으면 그 맥락을 우선 반영해 질문 의도에 맞게 답한다.
- 근거에 답이 없거나 불충분하면 지어내지 말고, 유쾌하게라도 "그건 기록에 없네요 ㅎㅎ"처럼 솔직히 모른다고 한다.
- 'Context'·'문서'·'ID' 같은 내부 표현은 노출하지 말고 자연스러운 문장으로 답한다.
- 인사·정체성 질문('살아있어?' 등)엔 근거 뒤지지 말고 ANNA답게 센스 있게 짧게 받아친다.
- 장황하지 않게, 간결하게."""


class QuestionResponse(MentionHandler):
    # 스레드 맥락 과다 방지: 가장 최근부터 이 글자 수까지만 포함
    THREAD_CONTEXT_MAX_CHARS = 4000

    def __init__(
        self,
        event,
        slack_client,
        qa_client: QAClient,
        require_prefix=True,
        assistant_id: Optional[str] = None,
    ):
        """require_prefix=True 면 `q)` 가 있을 때만 반응한다 (명령어보다 먼저 평가되는 명시적 질문).

        require_prefix=False 면 멘션 텍스트 전체를 질문으로 취급한다 — 셔플/새로운 빅챗/help
        등 어느 명령에도 걸리지 않은 멘션을 받아주는 체인 마지막 자리 전용. 빈 멘션은
        can_handle 이 False 라 기존 폴백(SimpleResponse)으로 넘어간다.
        """
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event.get("channel")
        # 스레드 안에서 멘션된 경우에만 thread_ts 가 존재
        self.thread_ts = event.get("thread_ts")
        self.slack_client = slack_client
        self.qa_client = qa_client
        self.require_prefix = require_prefix
        self.assistant_id = assistant_id or event.get("assistant_id")

    def handle_mention(self):
        if not self.can_handle():
            return False

        question = self._extract_question()
        if not question:
            self.slack_client.send_message(
                msg="질문을 이해하지 못했어요. `@anna q) <질문내용>` 형식으로 다시 시도해주세요.",
                ts=self.ts,
            )
            return True

        logger.info(f"Processing question: {question[:100]}...")

        conversation = self._fetch_conversation()
        if conversation:
            logger.info(
                "[q)] conversation context (%d messages)",
                len(conversation),
            )
        else:
            logger.info("[q)] no conversation context (top-level mention)")

        result = self.qa_client.chat(
            question=question,
            conversation=conversation,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
        )
        answer = self._render_result(result)
        logger.info("[q)] question=%r | answer=%r", question, answer)
        self.slack_client.send_message(msg=answer, ts=self.ts)

        return True

    @staticmethod
    def _render_result(result) -> str:
        """Render a QA result while accepting the old answer-only return value."""
        if result is None:
            return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요."
        if isinstance(result, str):
            return _strip_untrusted_answer_links(result, set())
        if not isinstance(result, ChatResult):
            return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요."

        if result.answer:
            answer = result.answer
        elif result.status == "insufficient_evidence":
            answer = "흐음~ 관련 기록에서는 확인하지 못했어요."
        elif result.status == "conflicting_evidence":
            answer = "흐음~ 기록이 서로 달라서 확답하기 어렵네요."
        else:
            answer = "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"
        cited_ids = {
            citation for citation in result.citations if isinstance(citation, str)
        }
        source_counts = Counter(source.document_id for source in result.sources)
        cited_sources = []
        seen = set()
        for source in result.sources:
            if (
                source.document_id not in cited_ids
                or source_counts[source.document_id] != 1
                or source.document_id in seen
            ):
                continue
            seen.add(source.document_id)
            url = _safe_source_url(source.url)
            if not url:
                continue
            label = _escape_slack_text(source.title or source.document_id)
            if source.timestamp:
                label = f"{label} · {_format_timestamp(source.timestamp)}"
            cited_sources.append(f"<{url}|{label}>")
        # The model sees source URLs in its context and may copy or invent links
        # in ``answer``.  Only links belonging to a cited source are trusted;
        # source links are rendered below from structured metadata.
        allowed_answer_urls = {
            _safe_source_url(source.url)
            for source in result.sources
            if source.document_id in cited_ids
            and source_counts[source.document_id] == 1
        }
        answer = _strip_untrusted_answer_links(answer, allowed_answer_urls)
        if cited_sources:
            answer += "\n\n출처: " + ", ".join(cited_sources)
        return answer

    def _fetch_conversation(self) -> List[Dict[str, str]]:
        """Gather bounded thread history as separately labeled conversation turns."""
        if not self.channel or not self.thread_ts:
            return []
        try:
            messages = self.slack_client.get_replies(
                channel=self.channel, thread_ts=self.thread_ts
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to fetch thread context: %s", e)
            return []

        normalized = []
        for message in messages or []:
            ts = self._message_value(message, "ts")
            # Slack may include the event itself in replies. Comparing ts is
            # stable even when the current text contains a different mention form.
            if ts and ts == self.ts:
                continue
            text = self._message_value(message, "text").strip()
            if not ts and text == self.text.strip():
                continue
            if not text:
                continue
            author = self._message_value(message, "user") or self._message_value(
                message, "author"
            )
            role = (
                "assistant" if self._is_assistant_message(message, author) else "user"
            )
            item = {"role": role, "content": text[:MAX_CONVERSATION_MESSAGE_CHARS]}
            if author:
                item["author"] = author[:MAX_CONVERSATION_AUTHOR_CHARS]
            if ts:
                item["timestamp"] = ts[:MAX_CONVERSATION_TIMESTAMP_CHARS]
            normalized.append(item)

        if not normalized:
            return []

        # Keep the root, turns matching the current question, and newest turns.
        # This retains both the topic and a useful middle reference when a long
        # thread would otherwise leave only the most recent messages.
        root = normalized[0]
        terms = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", self._extract_question().lower()))
        relevant = [
            item
            for item in normalized[1:]
            if any(term in item["content"].lower() for term in terms)
        ]
        recent = list(reversed(normalized[1:]))
        candidates = [root] + relevant + recent
        kept, total = [], 0
        for item in candidates:
            content = item["content"]
            if (
                len(kept) >= MAX_CONVERSATION_MESSAGES
                or total + len(content) > MAX_CONVERSATION_CHARS
            ):
                continue
            kept.append(item)
            total += len(content)
        kept_ids = {id(item) for item in kept}
        return [item for item in normalized if id(item) in kept_ids]

    def _fetch_thread_context(self) -> str:
        """Legacy text view retained for callers that used the old helper."""
        lines = []
        total = 0
        for item in self._fetch_conversation():
            line = f"{item.get('author', '')}: {item['content']}".strip(": ")
            if lines and total + len(line) + 1 > self.THREAD_CONTEXT_MAX_CHARS:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines)

    @staticmethod
    def _message_value(message: Any, key: str) -> str:
        if isinstance(message, dict):
            value = message.get(key, "")
        else:
            value = getattr(message, key, "")
        return value if isinstance(value, str) else ""

    def _is_assistant_message(self, message: Any, author: str) -> bool:
        return bool(
            (self.assistant_id and author == self.assistant_id)
            or self._message_value(message, "bot_id")
            or self._message_value(message, "subtype") == "bot_message"
        )

    def can_handle(self):
        if self.require_prefix:
            return "q)" in self.text.lower()
        return bool(self._extract_question())

    def _extract_question(self) -> str:
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", self.text).strip()
        match = QUESTION_PATTERN.search(clean_text)
        if match:
            return match.group(1).strip()
        if self.require_prefix:
            return ""
        return clean_text


def _safe_source_url(url: str) -> str:
    """Only put ordinary web URLs into Slack's angle-bracket link syntax."""
    if not isinstance(url, str) or any(char in url for char in "<>|"):
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
        trimmed = candidate.rstrip(".,!?;:")
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
