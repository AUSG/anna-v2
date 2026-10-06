# 다국어(한국어) 시스템 프롬프트 문자열이 길어, 이 파일은 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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
from implementation.web_search_client import WebSearchClient, WebSearchResult

logger = logging.getLogger(__name__)

# q) 이후의 질문을 추출하는 정규식
QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)
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

DEFAULT_SYSTEM_PROMPT = """너는 AUSG(AWSKRUG University Student Group) 커뮤니티의 멤버 같은 AI, ANNA야.
딱딱한 봇이 아니라 센스 있고 유쾌한 커뮤니티 멤버 한 명처럼 답해.
함께 주어지는 '현재 진행 중인 대화'와 '과거 커뮤니티 대화 기록'을 근거로 답한다.

원칙:
- 정확도가 우선이다. 근거를 종합해 핵심부터 답하고, 링크·일정 같은 구체 정보는 확인된 내용만 정확히 옮긴다.
- 기본은 한국어로 친근하고 자연스럽게 답한다. 영어 질문에는 영어로 답할 수 있고, 기술 용어·고유명사는 원어를 쓴다. 유머는 짧게 곁들이되 억지로 만들지 않는다.
- 현재 질문의 대상과 기간을 우선하고, 앞선 대화는 생략된 표현을 이해하는 데 활용한다.
- 함께 제공되는 근거 판단·출력 규칙을 말투보다 우선한다. 확인되지 않은 내용을 추측하거나 단정하지 말고, 이번에 찾은 기록에서는 확인하지 못했어요 또는 기록이 서로 달라 확답하기 어렵다고 짧게 말한다.
- 질문의 일부만 확인되면 확인된 부분만 먼저 답하고, 나머지는 확인하지 못했다고 간결하게 덧붙인다.
- 답변에 URL을 넣을 때는 제공된 근거에 포함된 확인된 링크만 그대로 사용한다. 일정 질문에는 날짜·시간·장소 등 확인된 정보만 짧게 정리한다.
- 출처 표기는 함께 제공되는 인용 규칙을 따른다.
- 'Context'·'문서'·'ID' 같은 내부 표현은 노출하지 말고 자연스러운 문장으로 답한다.
- 인사·정체성 질문('살아있어?' 등)엔 근거 뒤지지 말고 ANNA답게 센스 있게 짧게 받아친다.
- 장황하지 않게, 간결하게.

Slack 답변 형식:
- 첫 줄에 결론을 쓴다. 사실 하나를 묻는 질문은 1~3문장으로 끝낸다.
- 목록은 7개 이하로 쓴다. 표는 쓰지 않는다. 제목(#)은 여러 묶음으로 나뉘는 긴 답변에서만 쓴다.
- 링크는 [이름](URL) 형식으로 쓴다. 이모지는 답변 하나에 하나까지만 쓴다."""

# 웹 검색이 필요한지와 검색어를 LLM 이 정한다. 커뮤니티 기록에서 답을 못 찾은 질문에만 묻는다.
WEB_SEARCH_QUERY_PROMPT = """너는 질문을 웹 검색어로 바꾸는 도우미다.
주어지는 질문은 AUSG 커뮤니티의 슬랙 대화 기록에서는 답을 찾지 못한 질문이다.
웹 검색으로 답을 찾을 수 있는 질문이면 검색어 한 줄만 출력한다.

규칙:
- 앞선 대화에서 생략된 대상·기간·이름을 검색어에 보충한다. 검색어는 질문의 언어를 따른다.
- 커뮤니티 내부 일정·사람·채널·빅챗처럼 슬랙 기록에만 있을 내용, 인사·잡담·안나에 대한 질문처럼 웹 검색이 도움이 되지 않는 질문이면 NONE 만 출력한다.
- 설명·따옴표·접두어 없이 검색어 또는 NONE 만 출력한다."""

WEB_EVIDENCE_PROMPT = """

웹 검색 결과:
커뮤니티 대화 기록에서는 답을 찾지 못해 웹을 검색했다. 아래 결과를 근거로 답할 수 있으며, 그때는 웹에서 찾은 내용임을 짧게 밝힌다.
아래 결과의 URL 은 확인된 링크로 취급해 그대로 쓸 수 있다. 결과가 질문과 맞지 않으면 억지로 답하지 말고 확인하지 못했다고 한다.
검색어: {query}

{results}"""

# 검색어 결정에 함께 보내는 앞선 대화 길이. 생략된 지시어를 푸는 용도라 길 필요가 없다
WEB_SEARCH_CONTEXT_MAX_CHARS = 1500
WEB_SEARCH_QUERY_MAX_CHARS = 200


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
        web_search_client: Optional[WebSearchClient] = None,
    ):
        """require_prefix=True 면 `q)` 가 있을 때만 반응한다 (명령어보다 먼저 평가되는 명시적 질문).

        require_prefix=False 면 멘션 텍스트 전체를 질문으로 취급한다 — 셔플/새로운 빅챗/help
        등 어느 명령에도 걸리지 않은 멘션을 받아주는 체인 마지막 자리 전용. 빈 멘션은
        can_handle 이 False 라 기존 폴백(SimpleResponse)으로 넘어간다.

        web_search_client 가 있으면, 커뮤니티 기록에서 답을 못 찾은 질문(insufficient_evidence)에
        한해 웹을 검색하고 그 결과를 근거로 한 번 더 답한다. None 이면 웹 검색 없이 동작한다.
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
        self.web_search_client = web_search_client

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

        web_results: List[WebSearchResult] = []
        if self._needs_web_search(result):
            web_query, web_results = self._search_web(question, conversation)
            if web_results:
                logger.info(
                    "[q)] web search query=%r (%d results); asking again",
                    web_query,
                    len(web_results),
                )
                result = self.qa_client.chat(
                    question=question,
                    conversation=conversation,
                    system_prompt=DEFAULT_SYSTEM_PROMPT
                    + _format_web_evidence(web_query, web_results),
                )

        answer, sources = self._render_parts(result, web_results)
        logger.info("[q)] question=%r | answer=%r", question, answer)
        self.slack_client.send_answer(answer=answer, sources=sources, ts=self.ts)

        return True

    def _needs_web_search(self, result) -> bool:
        """QA 서버가 '기록에서 확인하지 못했다'고 판단한 질문만 웹으로 넘긴다.

        서버 장애(None)는 웹으로 메울 일이 아니고, 인사(no_search_needed)나 기록끼리 충돌하는
        경우(conflicting_evidence)는 웹이 답을 주지 않는다.
        """
        return (
            self.web_search_client is not None
            and isinstance(result, ChatResult)
            and result.status == "insufficient_evidence"
        )

    def _search_web(
        self, question: str, conversation: List[Dict[str, str]]
    ) -> Tuple[str, List[WebSearchResult]]:
        query = self._decide_web_query(question, conversation)
        if not query:
            logger.info("[q)] web search skipped: not a web-searchable question")
            return "", []
        try:
            results = self.web_search_client.search(query)
        except Exception as e:  # noqa: BLE001
            logger.warning("Web search failed: %s", e)
            return query, []
        if not results:
            logger.info("[q)] web search query=%r returned nothing", query)
        return query, results

    def _decide_web_query(
        self, question: str, conversation: List[Dict[str, str]]
    ) -> str:
        """LLM 에게 검색이 도움이 될지와 검색어를 묻는다. 판단에 실패하면 질문 그대로 검색한다."""
        content = f"질문: {question}"
        context = _recent_conversation_text(conversation)
        if context:
            content = f"앞선 대화:\n{context}\n\n{content}"
        try:
            decision = self.qa_client.generate(
                content=content, system_prompt=WEB_SEARCH_QUERY_PROMPT, max_tokens=64
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Web search query decision failed: %s", e)
            decision = None
        if decision is None:
            return question[:WEB_SEARCH_QUERY_MAX_CHARS]
        return _parse_web_query(decision)

    @staticmethod
    def _render_result(
        result, web_results: Optional[List[WebSearchResult]] = None
    ) -> str:
        """Render a QA result as one plain message (answer + source line)."""
        answer, sources = QuestionResponse._render_parts(result, web_results)
        if sources:
            answer += "\n\n출처: " + ", ".join(sources)
        return answer

    @staticmethod
    def _render_parts(
        result, web_results: Optional[List[WebSearchResult]] = None
    ) -> Tuple[str, List[str]]:
        """Return the cleaned answer and its Slack-formatted cited source links.

        The old answer-only return value is still accepted. ``web_results`` are the
        web pages the answer was given as evidence: their URLs are trusted in the
        answer and listed after the community sources.
        """
        web_results = list(web_results or [])
        if result is None:
            return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.", []
        if isinstance(result, str):
            return _strip_untrusted_answer_links(result, set()), []
        if not isinstance(result, ChatResult):
            return "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.", []

        if result.answer:
            answer = result.answer
        elif result.status == "insufficient_evidence" and web_results:
            answer = "흐음~ 관련 기록과 웹에서도 확인하지 못했어요."
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
            _safe_source_url(source.url)
            for source in result.sources
            if source.document_id in cited_ids
            and source_counts[source.document_id] == 1
        }
        for source in result.sources:
            if (
                source.document_id not in cited_ids
                or source_counts[source.document_id] != 1
            ):
                continue
            allowed_answer_urls.update(
                url
                for url in (
                    _safe_source_url(candidate) for candidate in source.evidence_urls
                )
                if url
            )
        # 웹 검색 결과는 모델에게 근거로 준 페이지들이다. 답변 안의 링크로 허용하고,
        # 답변이 실제로 인용한 페이지만 출처 줄에 붙인다.
        web_urls = {
            url for url in (_safe_source_url(r.url) for r in web_results) if url
        }
        allowed_answer_urls.update(web_urls)
        cited_sources.extend(_cited_web_sources(answer, web_results))
        return _strip_untrusted_answer_links(answer, allowed_answer_urls), cited_sources

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
            author = (
                self._message_value(message, "user")
                or self._message_value(message, "author")
                # 다른 봇(GeekNews 등)은 user 가 없다. 이름이라도 남겨야 누가 쓴 글인지 안다
                or self._message_value(message, "username")
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
        """안나 자신의 발화만 assistant 다.

        다른 봇의 글(GeekNews 스레드 첫 글 등)을 assistant 로 넣으면 요약할 원문이
        '안나가 했던 말'이 되어 근거에서 빠진다. 안나 id 를 모를 때만 봇 여부로 추정한다.
        """
        if self.assistant_id:
            return author == self.assistant_id
        return bool(
            self._message_value(message, "bot_id")
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


def _format_web_evidence(query: str, results: List[WebSearchResult]) -> str:
    """시스템 프롬프트 끝에 붙일 웹 검색 결과 블록."""
    lines = []
    for index, result in enumerate(results, start=1):
        head = f"{index}. {result.title or result.url}"
        if result.published_date:
            head += f" ({result.published_date})"
        lines.append(head)
        lines.append(f"   URL: {result.url}")
        if result.content:
            lines.append(f"   {result.content}")
    return WEB_EVIDENCE_PROMPT.format(query=query, results="\n".join(lines))


def _cited_web_sources(answer: str, results: List[WebSearchResult]) -> List[str]:
    """답변 본문이 링크로 인용한 웹 페이지만 출처 링크로 만든다.

    커뮤니티 출처는 서버가 citations 로 알려주지만 웹 결과는 그런 신호가 없다. 검색 결과 전부를
    출처로 달면 답과 무관한 페이지까지 섞이므로, 모델이 답변에 실제로 넣은 URL 만 고른다.
    """
    cited = []
    seen = set()
    for result in results:
        url = _safe_source_url(result.url)
        if not url or url in seen or url not in answer:
            continue
        seen.add(url)
        label = _escape_slack_text(result.title or url)
        cited.append(f"<{url}|{label} · 웹>")
    return cited


def _recent_conversation_text(conversation: List[Dict[str, str]]) -> str:
    """검색어 결정용으로 최근 대화를 짧게 요약한 텍스트 (최근 발화부터 거꾸로 채운다)."""
    lines: List[str] = []
    total = 0
    for item in reversed(conversation or []):
        content = item.get("content", "")
        if not content:
            continue
        line = f"{item.get('author', item.get('role', ''))}: {content}".strip(": ")
        if lines and total + len(line) + 1 > WEB_SEARCH_CONTEXT_MAX_CHARS:
            break
        lines.append(line[:WEB_SEARCH_CONTEXT_MAX_CHARS])
        total += len(line) + 1
    return "\n".join(reversed(lines))


def _parse_web_query(decision: str) -> str:
    """LLM 의 검색어 응답에서 첫 줄만 취한다. NONE 이면 빈 문자열(검색 안 함)."""
    for line in (decision or "").splitlines():
        line = line.strip().strip("`\"'“”‘’").strip()
        if not line:
            continue
        for prefix in ("검색어:", "query:", "Query:"):
            if line.startswith(prefix):
                line = line[len(prefix) :].strip()
        if line.upper() == "NONE" or not line:
            return ""
        return line[:WEB_SEARCH_QUERY_MAX_CHARS]
    return ""


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
