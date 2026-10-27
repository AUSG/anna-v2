# 다국어(한국어) 시스템 프롬프트 문자열이 길어, 이 파일은 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
import logging
from typing import Any, Dict, List, Optional, Tuple

from features.questions.models import (
    MAX_CONVERSATION_CHARS as MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_AUTHOR_CHARS,
    MAX_CONVERSATION_MESSAGE_CHARS,
    MAX_CONVERSATION_MESSAGES as MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATION_TIMESTAMP_CHARS,
    ChatResult as ChatResult,
    select_conversation,
)
from shared.mention_handler import MentionHandler
from features.questions.presentation.answers import (
    UNTRUSTED_LINK_MARKER as UNTRUSTED_LINK_MARKER,
    _escape_slack_text as _escape_slack_text,
    _format_timestamp as _format_timestamp,
    _normalize_answer_url as _normalize_answer_url,
    _safe_source_url as _safe_source_url,
    _strip_untrusted_answer_links as _strip_untrusted_answer_links,
    render_parts,
)
from slack_router import extract_question, matches_mention
from integrations.qa import QAClient

logger = logging.getLogger(__name__)

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


class QuestionResponse(MentionHandler):
    # 기존 텍스트 보기의 글자 수 기준
    THREAD_CONTEXT_MAX_CHARS = 4000

    def __init__(
        self,
        event,
        slack_client,
        qa_client: QAClient,
        require_prefix=True,
        assistant_id: Optional[str] = None,
    ):
        """require_prefix가 참이면 q) 질문만, 거짓이면 일반 질문 멘션도 받는다.

        빈 멘션은 받지 않는다.
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
        answer, sources = self._render_parts(result)
        logger.info("[q)] question=%r | answer=%r", question, answer)
        self.slack_client.send_answer(answer=answer, sources=sources, ts=self.ts)

        return True

    @staticmethod
    def _render_result(result) -> str:
        """답변과 출처를 한 메시지로 합친다."""
        answer, sources = QuestionResponse._render_parts(result)
        if sources:
            answer += "\n\n출처: " + ", ".join(sources)
        return answer

    @staticmethod
    def _render_parts(result) -> Tuple[str, List[str]]:
        """정리한 답변과 출처 링크를 반환한다. 구형 문자열 응답도 받는다."""
        return render_parts(result)

    def _fetch_conversation(self) -> List[Dict[str, str]]:
        """스레드 발화를 읽고 전송량에 맞춰 고른다."""
        if not self.channel or not self.thread_ts:
            return []
        try:
            messages = self.slack_client.get_replies(
                channel=self.channel, thread_ts=self.thread_ts
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to fetch thread context: %s", e)
            return []

        normalized = self._normalize_conversation(messages)
        if not normalized:
            return []
        return select_conversation(normalized, self._extract_question())

    def _normalize_conversation(self, messages) -> List[Dict[str, str]]:
        """SDK 응답을 발화로 바꾸고 필드별 길이를 제한한다."""
        normalized = []
        for message in messages or []:
            ts = self._message_value(message, "ts")
            # 멘션 표기가 달라도 현재 이벤트는 ts로 제외한다.
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
        return normalized

    def _fetch_thread_context(self) -> str:
        """기존 호출자를 위한 텍스트 보기를 만든다."""
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
        """안나 ID가 있으면 일치 여부로, 없으면 봇 표시로 발화를 구분한다."""
        if self.assistant_id:
            return author == self.assistant_id
        return bool(
            self._message_value(message, "bot_id")
            or self._message_value(message, "subtype") == "bot_message"
        )

    def can_handle(self):
        command = "explicit_question" if self.require_prefix else "question"
        return matches_mention(command, self.text)

    def _extract_question(self) -> str:
        return extract_question(self.text, require_prefix=self.require_prefix)
