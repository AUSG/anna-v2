from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_project_root() -> Path:
    return Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[
            f"{_get_project_root()}/env/.env.secret",
            f"{_get_project_root()}/env/.env.shared",
        ],
        env_file_encoding="utf-8",
    )

    # Slack bot API
    SLACK_SIGNING_SECRET: str = ""
    SLACK_BOT_TOKEN: str = ""

    # Google spreasheet
    # GCP API secrets
    GCP_type: str = ""
    GCP_project_id: str = ""
    GCP_private_key_id: str = ""
    GCP_private_key: str = ""
    GCP_client_email: str = ""
    GCP_client_id: str = ""
    GCP_auth_uri: str = ""
    GCP_token_uri: str = ""
    GCP_auth_provider_x509_cert_url: str = ""
    GCP_client_x509_cert_url: str = ""
    # Spreadsheet info
    FORM_SPREADSHEET_ID: str = ""
    MEMBERS_INFO_WORKSHEET_ID: int = 0

    # AUSG Slack channel info
    # channels
    ADMIN_CHANNEL: str = ""
    ANNOUNCEMENT_CHANNEL_ID: str = ""
    # Ids
    ANNA_ID: str = ""
    ORGANIZER_ID: str = ""
    # Emojis
    JOIN_BIGCHAT_EMOJI: str = ""

    # Development environment variables
    LOGLEVEL: str = "DEBUG"

    # vLLM settings
    VLLM_BASE_URL: str = ""
    VLLM_API_KEY: str = ""
    VLLM_MODEL: str = ""


envs = Settings()  # Singleton
