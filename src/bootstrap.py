"""의존성 조립과 지연 생성. feature는 이 모듈을 역으로 import하지 않는다."""

from slack_sdk import WebClient

from config.env_config import envs
from features.bigchat.slack import CreateBigchatSheet, RemindBigchatCommand
from features.bot_commands.slack import HelpResponse, ShuffleResponse, SimpleResponse
from features.issues.slack import CreateIssue
from features.members.services.directory import MemberManager
from features.questions.slack import QuestionResponse
from integrations.github import GithubClient
from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.qa import QAClient
from integrations.slack import SlackClient as SlackClient
from shared.mappings import search_value
from shared.slack_middleware import LoadingEmoji

MEMBER_MANAGER = None
QA_CLIENT = None


def create_web_client():
    return WebClient(token=envs.SLACK_BOT_TOKEN)


def _get_member_manager():
    global MEMBER_MANAGER
    if not MEMBER_MANAGER:
        MEMBER_MANAGER = MemberManager(GoogleSpreadsheetClient())
    return MEMBER_MANAGER


def _get_qa_client():
    global QA_CLIENT
    if not QA_CLIENT:
        QA_CLIENT = QAClient(
            qa_server_base_url=envs.QA_SERVER_BASE_URL, api_key=envs.QA_API_KEY
        )
    return QA_CLIENT


def _loading_emoji(slack_client, event):
    return LoadingEmoji(
        slack_client, search_value(event, "channel"), search_value(event, "ts")
    )


def create_mention_handler(command, event, slack_client):
    """명령에 필요한 핸들러와 외부 의존성만 생성한다."""
    match command:
        case "help":
            return HelpResponse(event, slack_client)
        case "shuffle":
            return ShuffleResponse(event, slack_client)
        case "explicit_question" | "question":
            return QuestionResponse(
                event,
                slack_client,
                _get_qa_client(),
                require_prefix=(command == "explicit_question"),
                assistant_id=envs.ANNA_ID,
            )
        case "create_issue":
            return CreateIssue(
                event, slack_client, GithubClient(envs.GITHUB_TOKEN, envs.GITHUB_REPO)
            )
        case "create_bigchat":
            return CreateBigchatSheet(
                event,
                slack_client,
                GoogleSpreadsheetClient(),
                _get_member_manager(),
                envs.JOIN_BIGCHAT_EMOJI,
            )
        case "reminder":
            return RemindBigchatCommand(
                event,
                slack_client,
                GoogleSpreadsheetClient(),
                _get_member_manager(),
                envs.ANNA_ID,
            )
        case "empty":
            return SimpleResponse(event, slack_client)
        case _:
            raise ValueError(f"Unknown mention command: {command}")
