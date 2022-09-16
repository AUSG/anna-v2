import logging
import os

from dotenv import load_dotenv

from exception.runtime_exception import RuntimeException

logger = logging.getLogger(__name__)


def _check(env_name: str, keys, invalidated_envs):
    if env_name not in keys:
        invalidated_envs.append(env_name)


def _validate():
    env_names = [
        'SLACK_BOT_TOKEN',
        'SLACK_SIGNING_SECRET',
        'GCP_type',
        'GCP_project_id',
        'GCP_private_key_id',
        'GCP_private_key',
        'GCP_client_email',
        'GCP_client_id',
        'GCP_auth_uri',
        'GCP_token_uri',
        'GCP_auth_provider_x509_cert_url',
        'GCP_client_x509_cert_url',
        'ANNOUNCEMENT_CHANNEL_ID',
        'ANNA_ID',
        'ORGANIZER_ID',
        'SUBMIT_FORM_EMOJI',
        'SUSPEND_FORM_EMOJI',
        'ADMIN_CHANNEL',
        'FORM_SPREADSHEET_ID',
        'MEMBERS_INFO_WORKSHEET_ID'
    ]

    invalidated_envs = []
    keys = os.environ.keys()

    # exists check
    for env_name in env_names:
        _check(env_name, keys, invalidated_envs)

    # other check
    if not os.environ.get('MEMBERS_INFO_WORKSHEET_ID').isnumeric():
        invalidated_envs.append('MEMBERS_INFO_WORKSHEET_ID')

    if len(invalidated_envs) > 0:
        raise RuntimeException(f"환경변수가 누락되었어요. invalidated_envs: {invalidated_envs}")


def init_env(base_path: str = "./"):
    load_dotenv(base_path + 'env/.env.shared')
    load_dotenv(base_path + 'env/.env.secret')

    _validate()

    logger.info("env configuration initialized")
