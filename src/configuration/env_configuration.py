import os
from pydantic import BaseSettings


## INFO: 공식문서에 따르면, 환경변수(`export A=B`)가 파일(`.env.XXX`)보다 우선순위가 높다.
class Settings(BaseSettings):
    # Slack bot API
    SLACK_SIGNING_SECRET: str = None
    SLACK_BOT_TOKEN: str = None

    # Google spreasheet
    ## GCP API secrets
    GCP_type: str = None
    GCP_project_id: str = None
    GCP_private_key_id: str = None
    GCP_private_key: str = None
    GCP_client_email: str = None
    GCP_client_id: str = None
    GCP_auth_uri: str = None
    GCP_token_uri: str = None
    GCP_auth_provider_x509_cert_url: str = None
    GCP_client_x509_cert_url: str = None
    ## Spreadsheet info
    FORM_SPREADSHEET_ID: str = None
    MEMBERS_INFO_WORKSHEET_ID: int = None

    # AUSG Slack channel info
    ## channels
    ADMIN_CHANNEL: str = None
    ANNOUNCEMENT_CHANNEL_ID: str = None
    ## Ids
    ANNA_ID: str = None
    ORGANIZER_ID: str = None
    ## Emojis
    SUBMIT_FORM_EMOJI: str = None
    SUSPEND_FORM_EMOJI: str = None

    # Development environment variables
    LOCAL: bool = False

    class Config:
        env_file = 'env/.env.secret', 'env/.env.shared'
        env_file_encoding = 'utf-8'


Configs = Settings() # Singleton
