"""참여 반응을 신청 시트의 행으로 옮긴다. Slack 은 모른다."""

from features.bigchat.models import Registration, RegistrationStatus
from features.members.ports import MemberDirectory
from shared.gateways import AppendOutcome, SheetsGateway


def register_applicant(
    user_id: str,
    worksheet_id: int,
    members: MemberDirectory,
    sheets: SheetsGateway,
) -> Registration:
    member = members.find(user_id)
    if member is None:
        return Registration(RegistrationStatus.MEMBER_NOT_FOUND)
    if not member.is_complete():
        return Registration(RegistrationStatus.MEMBER_LACKS_INFO)

    outcome = sheets.append_row_if_absent(
        worksheet_id, member.transform_for_spreadsheet()
    )
    if outcome is AppendOutcome.WORKSHEET_MISSING:
        return Registration(RegistrationStatus.WORKSHEET_MISSING)
    if outcome is AppendOutcome.ALREADY_PRESENT:
        # 일괄 등록과 동시에 처리됐거나 이벤트가 중복 전달된 경우
        return Registration(RegistrationStatus.ALREADY_REGISTERED, member)
    return Registration(RegistrationStatus.REGISTERED, member)
