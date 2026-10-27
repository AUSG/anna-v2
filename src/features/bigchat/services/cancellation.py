"""참여 반응이 사라지면 신청 시트에서 행을 지운다. Slack 은 모른다."""

from features.bigchat.models import CancellationStatus
from features.members.ports import MemberDirectory
from shared.gateways import SheetsGateway


def cancel_registration(
    user_id: str,
    worksheet_id: int,
    members: MemberDirectory,
    sheets: SheetsGateway,
) -> CancellationStatus:
    member = members.find(user_id)
    if member is None:
        return CancellationStatus.MEMBER_NOT_FOUND
    if not member.is_complete():
        return CancellationStatus.MEMBER_LACKS_INFO
    if not sheets.delete_row(worksheet_id, member.email):
        return CancellationStatus.WORKSHEET_MISSING
    return CancellationStatus.CANCELLED
