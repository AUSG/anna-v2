from typing import TYPE_CHECKING, List, Optional

from handler.mention_router import REMINDER_TRIGGER as TRIGGER
from util.bigchat_event import BigchatEvent
from util.utils import strip_multiline

if TYPE_CHECKING:
    from handler.bigchat.remind_bigchat import ReminderResult

# 이름 안의 줄구분자도 처리하므로 multiline literal 들여쓰기는 기존 값을 유지한다.
WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]
TEST_PHRASE = "테스트"
# 전원 발송은 되돌릴 수 없어서, 이 문구를 통째로 쳐야만 실행된다
BROADCAST_PHRASE = "지금 전원 발송"

USAGE = strip_multiline(
    f"""
    빅챗 리마인더를 저녁 6시까지 기다리지 않고 지금 돌릴 수 있어.
    - `{TRIGGER} {TEST_PHRASE} @받을사람`: 멘션한 사람에게만 보내볼게 (발송이 되는지 확인용)
    - `{TRIGGER} {BROADCAST_PHRASE}`: 내일 빅챗 신청자 *전원*에게 진짜로 보낼게"""
)


def missing_targets_message(user: str) -> str:
    return strip_multiline(
        f"""
                    받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.
                    예) `{TRIGGER} {TEST_PHRASE} <@{user}>`
                    (진짜로 전원에게 보내려면 `{TRIGGER} {BROADCAST_PHRASE}` 라고 해줘!)"""
    )


def build_reminder(event: BigchatEvent) -> str:
    d = event.start
    when = (
        f"{d.month}월 {d.day}일 ({WEEKDAYS_KO[d.weekday()]}) "
        f"{d.strftime('%H:%M')}~{event.end.strftime('%H:%M')}"
    )
    # 시트 이름이 "빅챗 26-08-18 ..." 이면 이벤트 이름이 그냥 "빅챗" 이라
    # 그대로 쓰면 "*빅챗* 빅챗이 열리는 날이야" 처럼 겹친다.
    # 어느 쪽이든 '빅챗' 으로 끝나므로 뒤에 붙는 조사는 항상 '이'.
    subject = f"*{event.name}*" if event.name.endswith("빅챗") else f"*{event.name}* 빅챗"
    return strip_multiline(
        f"""
            :wave: 안녕! 내일 {subject}이 열리는 날이야.
            :calendar: {when}
            잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"""
    )


def build_report(result: "ReminderResult", targets: Optional[List[str]]) -> str:
    if not result.bigchat_names:
        return strip_multiline(
            f"""
                {result.target_date} 에 시작하는 빅챗을 못 찾았어. 그래서 보낼 것도 없었어.
                - 빅챗 이름 형식(`<이름> yy-MM-DD HH:mm~HH:mm`)으로 읽힌 시트: {result.parsed_sheet_cnt}개
                - 형식이 안 맞아서 무시한 시트: {result.ignored_sheet_cnt}개
                시트 이름이 이 형식인지 확인해줘! 자세한 목록은 로그에 남겼어."""
        )

    found = ", ".join(result.bigchat_names)
    unresolved = result.applicant_cnt - result.resolved_cnt
    unresolved_note = (
        f"\n신청자 {unresolved}명은 멤버 시트에서 슬랙 계정을 못 찾아서 못 보냈어. (누군지는 로그에 남겼어!)"
        if unresolved
        else ""
    )
    if targets is None:
        return strip_multiline(
            f"""
                {result.target_date} 빅챗 `{found}` 신청자들에게 리마인더를 보냈어!
                - 신청 시트에서 찾은 신청자: {result.applicant_cnt}명
                - 실제로 DM 을 보낸 사람: {result.sent_cnt}명{unresolved_note}"""
        )

    target_txt = ", ".join(f"<@{user_id}>" for user_id in targets)
    return strip_multiline(
        f"""
            {result.target_date} 빅챗 `{found}` 찾았어!
            테스트 DM 을 {target_txt} 에게 보냈어 ({result.sent_cnt}건).
            실제 발송이었다면 이렇게 나갔을 거야:
            - 신청 시트에서 찾은 신청자: {result.applicant_cnt}명
            - 그 중 멤버 시트에서 슬랙 계정을 찾은 사람: {result.resolved_cnt}명
            (둘이 다르면 신청 시트 이메일과 멤버 시트 이메일이 안 맞는 거야. 로그에 누군지 남겼어!)"""
    )
