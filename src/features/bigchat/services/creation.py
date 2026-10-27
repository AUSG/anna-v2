from features.bigchat.models import BigchatCreated, CreateBigchatCommand
from shared.gateways import SheetsGateway


def create_bigchat(
    command: CreateBigchatCommand, sheets: SheetsGateway
) -> BigchatCreated:
    worksheet_id = sheets.create_bigchat_sheet(command.sheet_name)
    return BigchatCreated(
        worksheet_id=worksheet_id,
        sheet_name=command.sheet_name,
        sheet_url=sheets.get_url(worksheet_id),
    )
