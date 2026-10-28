"""앱 생성과 의존성 조립. import만으로 외부 연결이나 스케줄러를 시작하지 않는다."""

import logging
from functools import partial
from threading import Lock

from flask import Flask
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient

from config.env_config import Settings, envs
from config.log_config import init_logger
from features.bigchat.calendar import KST
from features.bigchat.handlers.abandon_bigchat import AbandonBigchat
from features.bigchat.handlers.create_bigchat_modal import (
    OpenCreateBigchatModal,
    SubmitCreateBigchatModal,
)
from features.bigchat.handlers.create_bigchat_sheet import CreateBigchatSheet
from features.bigchat.handlers.join_bigchat import JoinBigchat
from features.bigchat.handlers.remind_bigchat_command import RemindBigchatCommand
from features.bigchat.services.calendar import BigchatCalendar
from features.bigchat.services.reminders import RemindBigchat
from features.bot_commands.handlers.help_response import HelpResponse
from features.bot_commands.handlers.shuffle_response import ShuffleResponse
from features.bot_commands.handlers.simple_response import SimpleResponse
from features.community.handlers.announce_new_channel_created import (
    AnnounceNewChannelCreated,
)
from features.community.handlers.subin_like_response import SubinLikeResponse
from features.issues.handlers.create_issue import CreateIssue
from features.members.services.directory import MemberManager
from features.questions.handlers.question_response import QuestionResponse
from http_routes import register_http_routes
from integrations.github import GithubClient
from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.qa import QAClient
from jobs import ScheduledJob, post_daily_digest, remind_bigchat
from shared.scheduling import DailyScheduler
from slack_events import SlackHandlers, register_slack_handlers

logger = logging.getLogger(__name__)


class Services:
    """앱 범위의 지연 의존성. 이벤트 입력이나 SDK 요청 컨텍스트는 보관하지 않는다."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._members = None
        self._qa = None
        self._members_lock = Lock()
        self._qa_lock = Lock()

    def sheets(self) -> GoogleSpreadsheetClient:
        # 기존처럼 사용 시 생성한다. 도움말과 잘못된 캘린더 토큰에는 인증이 필요 없다.
        return GoogleSpreadsheetClient(settings=self.settings)

    def members(self) -> MemberManager:
        with self._members_lock:
            if self._members is None:
                self._members = MemberManager(
                    self.sheets(), worksheet_id=self.settings.MEMBERS_INFO_WORKSHEET_ID
                )
            return self._members

    def qa(self) -> QAClient:
        with self._qa_lock:
            if self._qa is None:
                self._qa = QAClient(
                    qa_server_base_url=self.settings.QA_SERVER_BASE_URL,
                    api_key=self.settings.QA_API_KEY,
                )
            return self._qa

    def github(self) -> GithubClient:
        return GithubClient(self.settings.GITHUB_TOKEN, self.settings.GITHUB_REPO)

    def web_client(self) -> WebClient:
        return WebClient(token=self.settings.SLACK_BOT_TOKEN)

    def calendar(self) -> BigchatCalendar:
        return BigchatCalendar(
            worksheet_title=lambda worksheet_id: self.sheets().get_worksheet_title(
                worksheet_id
            ),
            permalink=lambda channel, ts: self.web_client().chat_getPermalink(
                channel=channel, message_ts=ts
            )["permalink"],
            intro=lambda channel, ts: self.web_client().conversations_replies(
                channel=channel, ts=ts, limit=1
            )["messages"][0]["text"],
        )


def build_slack_handlers(services: Services) -> SlackHandlers:
    settings = services.settings
    return SlackHandlers(
        mentions={
            "help": lambda ctx: HelpResponse(ctx.event, ctx.slack_client),
            "shuffle": lambda ctx: ShuffleResponse(ctx.event, ctx.slack_client),
            "explicit_question": lambda ctx: QuestionResponse(
                ctx.event,
                ctx.slack_client,
                services.qa(),
                require_prefix=True,
                assistant_id=settings.ANNA_ID,
            ),
            "question": lambda ctx: QuestionResponse(
                ctx.event,
                ctx.slack_client,
                services.qa(),
                require_prefix=False,
                assistant_id=settings.ANNA_ID,
            ),
            "create_issue": lambda ctx: CreateIssue(
                ctx.event, ctx.slack_client, services.github()
            ),
            "create_bigchat": lambda ctx: CreateBigchatSheet(
                ctx.event,
                ctx.slack_client,
                services.sheets(),
                services.members(),
                settings.JOIN_BIGCHAT_EMOJI,
            ),
            "reminder": lambda ctx: RemindBigchatCommand(
                ctx.event,
                ctx.slack_client,
                services.sheets(),
                services.members(),
                settings.ANNA_ID,
            ),
            "empty": lambda ctx: SimpleResponse(ctx.event, ctx.slack_client),
        },
        join_bigchat=lambda ctx: JoinBigchat(
            ctx.event,
            settings.JOIN_BIGCHAT_EMOJI,
            ctx.slack_client,
            services.sheets(),
            services.members(),
            loading_emoji=ctx.loading_emoji,
            settings=settings,
        ),
        abandon_bigchat=lambda ctx: AbandonBigchat(
            ctx.event,
            settings.JOIN_BIGCHAT_EMOJI,
            ctx.slack_client,
            services.sheets(),
            loading_emoji=ctx.loading_emoji,
        ),
        announce_new_channel_created=lambda ctx: AnnounceNewChannelCreated(
            ctx.event, ctx.slack_client
        ),
        subin_like_response=lambda ctx: SubinLikeResponse(
            ctx.event, ctx.slack_client, services.qa(), anna_id=settings.ANNA_ID
        ),
        open_create_bigchat_modal=lambda ctx: OpenCreateBigchatModal(
            ctx.event, ctx.web_client
        ),
        submit_create_bigchat_modal=lambda ctx: SubmitCreateBigchatModal(
            ctx.event,
            ctx.ack,
            ctx.slack_client,
            services.sheets(),
            services.members(),
            settings.JOIN_BIGCHAT_EMOJI,
        ),
    )


def build_jobs(services: Services) -> tuple[ScheduledJob, ...]:
    settings = services.settings
    jobs = []
    if settings.BIGCHAT_REMINDER_ENABLED:
        jobs.append(
            ScheduledJob(
                name="bigchat-reminder",
                hour=18,
                minute=0,
                callback=partial(
                    remind_bigchat,
                    web_client_factory=services.web_client,
                    send_reminders=lambda slack: RemindBigchat(
                        slack, services.sheets(), services.members()
                    ).run(),
                    admin_channel=settings.ADMIN_CHANNEL,
                ),
            )
        )
    if settings.DAILY_DIGEST_ENABLED:
        jobs.append(
            ScheduledJob(
                name="daily-digest",
                hour=10,
                minute=0,
                callback=partial(
                    post_daily_digest,
                    web_client_factory=services.web_client,
                    fetch_digest=lambda: services.qa().daily_digest(),
                    channel=settings.DAILY_DIGEST_CHANNEL_ID,
                    admin_channel=settings.ADMIN_CHANNEL,
                ),
            )
        )
    return tuple(jobs)


def create_app(settings: Settings = envs, *, bolt_app=None) -> Flask:
    """라우트와 factory를 조립한다. 예약 작업 시작은 start_jobs로 분리한다."""
    init_logger(settings.LOGLEVEL)
    services = Services(settings)
    bolt_app = (
        bolt_app
        if bolt_app is not None
        else App(
            token=settings.SLACK_BOT_TOKEN, signing_secret=settings.SLACK_SIGNING_SECRET
        )
    )
    register_slack_handlers(
        bolt_app, build_slack_handlers(services), admin_channel=settings.ADMIN_CHANNEL
    )
    flask_app = Flask(__name__)
    register_http_routes(
        flask_app, SlackRequestHandler(bolt_app), services.calendar(), settings
    )
    flask_app.extensions["anna_services"] = services
    flask_app.extensions["anna_jobs"] = build_jobs(services)
    flask_app.extensions["anna_schedulers"] = {}
    flask_app.extensions["anna_jobs_lock"] = Lock()
    return flask_app


def start_jobs(flask_app: Flask):
    """worker 시작 시 명시적으로 호출한다. 같은 앱에서는 여러 번 호출해도 한 번만 시작한다."""
    with flask_app.extensions["anna_jobs_lock"]:
        schedulers = flask_app.extensions["anna_schedulers"]
        for job in flask_app.extensions["anna_jobs"]:
            if job.name in schedulers:
                continue
            scheduler = DailyScheduler(
                job=job.callback,
                hour=job.hour,
                minute=job.minute,
                tz=KST,
                name=job.name,
            )
            scheduler.start()
            schedulers[job.name] = scheduler
            logger.info(
                "%s scheduler started (daily %02d:%02d KST)",
                job.name,
                job.hour,
                job.minute,
            )
        return tuple(schedulers.values())


if __name__ == "__main__":
    flask_app = create_app()
    start_jobs(flask_app)
    logger.info("Anna wakes up at room %d", 8080)
    flask_app.run(host="0.0.0.0", port=8080)
