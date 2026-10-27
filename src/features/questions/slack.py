# 다국어(한국어) 시스템 프롬프트 문자열이 길어, 이 파일은 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
import logging
from typing import List

from features.questions.models import Question, Utterance
from features.questions.ports import QAGateway
from features.questions.presentation.answers import render_parts
from features.questions.services.conversation import (
    normalize_conversation,
    select_conversation,
)
from shared.gateways import SlackGateway
from shared.slack_events import MentionEvent

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

UNPARSEABLE_QUESTION_MESSAGE = "질문을 이해하지 못했어요. `@anna q) <질문내용>` 형식으로 다시 시도해주세요."


def answer_question(
    command: Question,
    event: MentionEvent,
    slack: SlackGateway,
    qa: QAGateway,
    *,
    assistant_id: str,
) -> bool:
    if not command.text:
        slack.send_thread_message(event.channel, event.ts, UNPARSEABLE_QUESTION_MESSAGE)
        return True

    logger.info(f"Processing question: {command.text[:100]}...")
    conversation = fetch_conversation(
        command.text, event, slack, assistant_id=assistant_id
    )
    if conversation:
        logger.info("[q)] conversation context (%d messages)", len(conversation))
    else:
        logger.info("[q)] no conversation context (top-level mention)")

    result = qa.chat(
        question=command.text,
        conversation=conversation,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
    )
    answer, sources = render_parts(result)
    logger.info("[q)] question=%r | answer=%r", command.text, answer)
    slack.send_answer(event.channel, event.ts, answer, sources)
    return True


def fetch_conversation(
    question: str, event: MentionEvent, slack: SlackGateway, *, assistant_id: str
) -> List[Utterance]:
    """스레드 발화를 읽고 전송량에 맞춰 고른다. 스레드 밖 멘션이면 빈 목록."""
    if not event.thread_ts:
        return []
    try:
        messages = slack.get_thread(event.channel, event.thread_ts)
    except Exception as e:
        logger.warning("Failed to fetch thread context: %s", e)
        return []
    normalized = normalize_conversation(
        messages, current_ts=event.ts, assistant_id=assistant_id
    )
    return select_conversation(normalized, question)
