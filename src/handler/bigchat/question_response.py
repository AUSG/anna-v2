import logging
import re

from handler.bigchat.mention_handler import MentionHandler
from implementation.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

# q) 이후의 질문을 추출하는 정규식
QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)

DEFAULT_SYSTEM_PROMPT = """당신은 AUSG(AWSKRUG University Student Group) 커뮤니티의 친절한 도우미 ANNA입니다.
질문에 대해 명확하고 도움이 되는 답변을 제공해주세요. 질문에 맞게 영어 또는 한국어로 답변해주세요.
답변은 간결하면서도 충분한 정보를 담아주세요."""


class QuestionResponse(MentionHandler):
    def __init__(self, event, slack_client, llm_client: LLMClient):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client
        self.llm_client = llm_client

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

        try:
            answer = self.llm_client.chat(question=question, system_prompt=DEFAULT_SYSTEM_PROMPT)
            self.slack_client.send_message(msg=answer, ts=self.ts)
        except LLMError as e:
            self.slack_client.send_message(msg=str(e), ts=self.ts)

        return True

    def can_handle(self):
        text_lower = self.text.lower()
        return "q)" in text_lower

    def _extract_question(self) -> str:
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", self.text).strip()
        match = QUESTION_PATTERN.search(clean_text)
        if match:
            return match.group(1).strip()
        return ""
