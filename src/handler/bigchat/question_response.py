# 다국어(한국어) 시스템 프롬프트 문자열이 길어, 이 파일은 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
import logging
import re

from handler.bigchat.mention_handler import MentionHandler
from implementation.qa_client import QAClient

logger = logging.getLogger(__name__)

# q) 이후의 질문을 추출하는 정규식
QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)

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

    def __init__(self, event, slack_client, qa_client: QAClient, require_prefix=True):
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

        thread_context = self._fetch_thread_context()
        if thread_context:
            logger.info(
                "[q)] thread context (%d chars):\n%s",
                len(thread_context),
                thread_context,
            )
            augmented = (
                f"[현재 진행 중인 대화]\n{thread_context}\n\n" f"[위 대화에 대한 질문] {question}"
            )
        else:
            logger.info("[q)] no thread context (top-level mention)")
            augmented = question

        answer = self.qa_client.chat(
            question=augmented, system_prompt=DEFAULT_SYSTEM_PROMPT
        )
        if answer is None:
            answer = "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아가볼까?"
        logger.info("[q)] question=%r | answer=%r", question, answer)
        self.slack_client.send_message(msg=answer, ts=self.ts)

        return True

    def _fetch_thread_context(self) -> str:
        """멘션이 스레드 안에서 일어난 경우, 그 스레드의 대화를 맥락으로 수집."""
        if not self.channel or not self.thread_ts:
            return ""
        try:
            messages = self.slack_client.get_replies(
                channel=self.channel, thread_ts=self.thread_ts
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to fetch thread context: %s", e)
            return ""

        lines = []
        for m in messages:
            text = re.sub(r"<@[A-Z0-9]+>", "", m.text or "").strip()
            if text:
                lines.append(f"{m.user}: {text}")

        # 과다 방지: 글자수가 아니라 메시지 단위로 자른다 (메시지 중간이 끊기지 않도록).
        # 최근 메시지부터 채우고, budget 을 넘기는 오래된 메시지는 통째로 제외.
        kept, total = [], 0
        for line in reversed(lines):
            if kept and total + len(line) + 1 > self.THREAD_CONTEXT_MAX_CHARS:
                break
            kept.append(line)
            total += len(line) + 1
        return "\n".join(reversed(kept))

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
