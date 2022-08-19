import logging
import os

from dotenv import load_dotenv

from exception.runtime_exception import RuntimeException

logger = logging.getLogger(__name__)


def _validate():
    invalidated_envs = []
    keys = os.environ.keys()

    # .env.secret
    if 'SLACK_BOT_TOKEN' not in keys:
        invalidated_envs.append('SLACK_BOT_TOKEN')
    if 'SLACK_SIGNING_SECRET' not in keys:
        invalidated_envs.append('SLACK_SIGNING_SECRET')
    if 'GCP_type' not in keys:
        invalidated_envs.append('GCP_type')
    if 'GCP_project_id' not in keys:
        invalidated_envs.append('GCP_project_id')
    if 'GCP_private_key_id' not in keys:
        invalidated_envs.append('GCP_private_key_id')
    if 'GCP_private_key' not in keys:
        invalidated_envs.append('GCP_private_key')
    if 'GCP_client_email' not in keys:
        invalidated_envs.append('GCP_client_email')
    if 'GCP_client_id' not in keys:
        invalidated_envs.append('GCP_client_id')
    if 'GCP_auth_uri' not in keys:
        invalidated_envs.append('GCP_auth_uri')
    if 'GCP_token_uri' not in keys:
        invalidated_envs.append('GCP_token_uri')
    if 'GCP_auth_provider_x509_cert_url' not in keys:
        invalidated_envs.append('GCP_auth_provider_x509_cert_url')
    if 'GCP_client_x509_cert_url' not in keys:
        invalidated_envs.append('GCP_client_x509_cert_url')

    # .env.shared
    if 'ANNOUNCEMENT_CHANNEL_ID' not in keys:
        invalidated_envs.append('ANNOUNCEMENT_CHANNEL_ID')
    if 'ANNA_ID' not in keys:
        invalidated_envs.append('ANNA_ID')
    if 'SUBMIT_FORM_EMOJI' not in keys:
        invalidated_envs.append('SUBMIT_FORM_EMOJI')
    if 'ADMIN_CHANNEL' not in keys:
        invalidated_envs.append('ADMIN_CHANNEL')
    if 'FORM_SPREADSHEET_ID' not in keys:
        invalidated_envs.append('FORM_SPREADSHEET_ID')
    if 'MEMBERS_INFO_WORKSHEET_ID' not in keys \
            or not os.environ.get('MEMBERS_INFO_WORKSHEET_ID').isnumeric():
        invalidated_envs.append('MEMBERS_INFO_WORKSHEET_ID')

    if len(invalidated_envs) > 0:
        raise RuntimeException(f"환경변수가 누락되었어요. invalidated_envs: {invalidated_envs}")


def init_env(base_path: str = "./"):
    load_dotenv(base_path + '/.env.shared')
    load_dotenv(base_path + '/.env.secret')

    _validate()

    logger.info("env configuration initialized")
