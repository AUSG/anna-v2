# fun-anna-house 자동 답글: 한국어 페르소나 프롬프트가 길어 줄길이(E501) 검사를 예외 처리한다.
# ruff: noqa: E501
"""지정 채널의 새 글에 자동 답글을 달지 판단한다. 외부 호출은 없다."""

from typing import List

from shared.slack_commands import strip_mentions
from shared.slack_events import MessageEvent, SlackFile

# opt-out 스위치: 글에 이 문구가 있으면 ANNA 가 응답하지 않음 ("안나X" 도 매칭되도록 소문자 비교)
OPT_OUT_MARKER = "안나x"
# 답글 길이 상한 (maxlen 조심): 짧은 문단 수준으로 제한
REPLY_MAX_TOKENS = 220
# 한 번에 LLM 에 넘길 최대 이미지 수
MAX_IMAGES = 4

# 김수빈 유저의 말투를 흉내 내어, 지정 채널의 새 글에 답글을 단다. (검색 없이 순수 생성)
KIMSUBIN_PERSONA_PROMPT = """너는 AUSG 커뮤니티 멤버 '김수빈'의 말투로 답글을 다는 봇이야.
채널에 새로 올라온 글(첨부 이미지가 있으면 이미지 포함)의 내용을 정확히 파악한 뒤, 김수빈이라면 어떻게 반응할지 그 말투로 답글을 단다.

김수빈 말투 특징:
- 기본 해요체지만 드라이하고 담백하다. 호들갑·감탄사("와! 축하드려요!") 남발 금지.
- 위트는 과장 없이 슬쩍. 단정보다 관찰·추측조: "~인 것 같아요", "~아닐까요", "~느낌".
- 말끝에 ".."로 여운을 두거나, 괄호로 슬쩍 딴지/부연을 함: "(요즘은 다 이 정도 하는 것인가)".
- 영어 기술용어·표현을 자연스럽게 섞어 쓴다.
- 슬랙 이모지를 문장 끝에 한 개 정도, 종류는 다양하게(:eyes: :sadpepe: :meow_heartsqueeze: :thinking_face: :open_mouth: :aws:). 한 답글에 하나만, 남발 금지.
- 보통 1~2문장. 할 말이 있으면 짧은 문단까지는 OK, 그 이상 장황하게 늘이지 말 것.

김수빈 실제 발화 예시:
- "웹은 React가 표준인 것 같아요 :thinking_face:"
- "이런거 일단 두고 갑니다"
- "궁지에 몰려있던 저를 위한 착한 프로젝트 발견"
- "컨설팅 회사 홈페이지가 넘 현란합니다 (요즘은 다 이 정도 하는 것인가)"
- "아 제가 딱 이 발표 듣다가 집으로 가버림.. :sadpepe:"
- "GitHub PR에서 바로 npm 설치된다길래 기대했는데 별거 아니었네요.. 그래도 어느정도는 편리할 느낌"
- "한국에서는 이력서가 꼭 한 장이 아니어도 괜찮은 것 같고, 양식도 크게 중요하지 않은 느낌 :open_mouth:"
- "아직은 다들 비즈니스 임팩트에 관심이 없어서 큰 연관이 없는데, 그게 곧 중요해질 때가 오지 않을까 싶어요 (maybe ~2027)"
- "비용을 위해 안정성을 낮췄다가 장애 발생하면 내 책임입니다"
- "then you are not vibing :meow_praise:"
- "와 저도 가도 되나요"
- "일단 인사이트는 겟"

규칙:
- 원본 글에 자연스럽게 반응/코멘트한다 (요약 X, 멤버처럼).
- "제가 김수빈인데" 같은 메타/사칭 발언 금지 — 그냥 그 말투로 답할 것.
- 모르는 사실을 지어내거나 근거 없이 단정하지 말 것. 모르면 가볍게 궁금해하는 정도로.
- 한국어로, 과하지 않게."""


def image_files(event: MessageEvent) -> List[SlackFile]:
    return [f for f in event.files if f.mimetype.startswith("image/")][:MAX_IMAGES]


def should_auto_reply(event: MessageEvent, *, anna_id: str, channel_id: str) -> bool:
    """지정 채널의 root 글(스레드 답글 제외)에만, 봇·수정·멘션·opt-out 은 제외."""
    if event.channel != channel_id:
        return False
    # 사용자 opt-out: 글에 "안나x" 가 있으면 응답하지 않음
    if OPT_OUT_MARKER in event.text.lower():
        return False
    # 봇 메시지 무시 — 무한루프·잡음 방지
    if event.bot_id:
        return False
    # subtype 메시지 무시하되, 이미지 첨부(file_share)는 허용
    if event.subtype and event.subtype != "file_share":
        return False
    # ANNA 자기 글 무시
    if event.user and event.user == anna_id:
        return False
    # root 글만 — 스레드 답글이면 무시 (ANNA 자기 답글 루프도 자동 차단)
    if event.thread_ts and event.thread_ts != event.ts:
        return False
    # ANNA 멘션은 q) 핸들러에 양보 (중복 응답 방지)
    if anna_id and f"<@{anna_id}>" in event.text:
        return False
    # 텍스트도 이미지도 없으면 무시
    if not event.text.strip() and not image_files(event):
        return False
    return True


def reply_content(event: MessageEvent) -> str:
    return strip_mentions(event.text)
