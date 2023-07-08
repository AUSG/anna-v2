from pydantic import BaseSettings


class Settings(BaseSettings):
    # Slack bot API
    SLACK_SIGNING_SECRET: str = None
    SLACK_BOT_TOKEN: str = None

    # Google spreasheet
    # GCP API secrets
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
    # Spreadsheet info
    FORM_SPREADSHEET_ID: str = None
    MEMBERS_INFO_WORKSHEET_ID: int = None

    # AUSG Slack channel info
    # channels
    ADMIN_CHANNEL: str = None
    ANNOUNCEMENT_CHANNEL_ID: str = None
    # Ids
    ANNA_ID: str = None
    ORGANIZER_ID: str = None
    # Emojis
    JOIN_BIGCHAT_EMOJI: str = None
    ABANDON_BIGCHAT_EMOJI: str = None
    SUSPEND_FORM_EMOJI: str = None

    # Development environment variables
    LOGLEVEL: str = "DEBUG"

    class Config:
        env_file = "env/.env.secret", "env/.env.shared"
        env_file_encoding = "utf-8"


envs = Settings()  # Singleton
