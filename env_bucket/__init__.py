import os

from dotenv import load_dotenv

load_dotenv()

_bucket = {
    'SLACK_BOT_TOKEN': os.environ.get('SLACK_BOT_TOKEN'),
    'SLACK_SIGNING_SECRET': os.environ.get('SLACK_SIGNING_SECRET'),
    'ANNOUNCEMENT_CHANNEL_ID': os.environ.get('ANNOUNCEMENT_CHANNEL_ID'),
    'ANNA_ID': os.environ.get('ANNA_ID'),
    'SUBMIT_FORM_EMOJI': os.environ.get('SUBMIT_FORM_EMOJI'),
    'ADMIN_CHANNEL': os.environ.get('ADMIN_CHANNEL'),
    'FORM_SPREADSHEET_ID': os.environ.get('FORM_SPREADSHEET_ID'),
    'MEMBERS_INFO_WORKSHEET_ID': os.environ.get('MEMBERS_INFO_WORKSHEET_ID'),
}


def get(key):
    return _bucket.get(key)
