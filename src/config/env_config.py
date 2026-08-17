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

    # QnA API settings
    QA_SERVER_BASE_URL: str = ""
    QA_API_KEY: str = ""

    # Bigchat calendar buttons (#112)
    PUBLIC_BASE_URL: str = "https://anna-v2-2023.fly.dev"
    ICS_TOKEN_SECRET: str = ""  # 비어 있으면 ics 버튼/엔드포인트 비활성화

    # Bigchat reminder DM (빅챗 전날 저녁 신청자들에게 발송)
    # 로컬 개발 중 프로덕션과 중복 발송되지 않게 하려면 false 로 끈다
    BIGCHAT_REMINDER_ENABLED: bool = True


envs = Settings()  # Singleton
