"""커뮤니티 새 글과 채널 생성 이벤트 진입점."""

import base64
import logging

from features.community.presentation.messages import new_channel_message
from features.community.services.auto_reply import (
    KIMSUBIN_PERSONA_PROMPT,
    REPLY_MAX_TOKENS,
    image_files,
    reply_content,
    should_auto_reply,
)
from features.questions.ports import QAGateway
from runtime import Runtime
from shared.error_boundary import report_failure
from shared.gateways import SlackGateway
from shared.slack_events import ChannelCreatedEvent, MessageEvent, is_edited_message

logger = logging.getLogger(__name__)


def announce_new_channel_created(
    event: ChannelCreatedEvent, slack: SlackGateway, *, freetalk_channel: str
) -> bool:
    slack.send_channel_message(freetalk_channel, new_channel_message(event.channel_id))
    return True


def subin_like_response(
    event: MessageEvent,
    slack: SlackGateway,
    qa: QAGateway,
    *,
    anna_id: str,
    channel_id: str,
) -> bool:
    """지정 채널(fun-anna-house)의 root 글에 김수빈 말투로 답글. (검색 없이 순수 생성)"""
    if not should_auto_reply(event, anna_id=anna_id, channel_id=channel_id):
        return False

    content = reply_content(event)
    images = _download_images(event, slack)
    answer = qa.generate(
        content=content,
        system_prompt=KIMSUBIN_PERSONA_PROMPT,
        max_tokens=REPLY_MAX_TOKENS,
        images=images or None,
    )
    if not answer:
        logger.info("[subin] generation failed/empty, skip")
        return False

    logger.info(
        "[subin] post=%r images=%d | reply=%r", content[:80], len(images), answer
    )
    slack.send_thread_message(event.channel, event.ts, answer)
    return True


def _download_images(event: MessageEvent, slack: SlackGateway):
    """첨부 이미지를 봇 토큰으로 받아 base64 data URL 리스트로."""
    out = []
    for f in image_files(event):
        if not f.url:
            continue
        data = slack.download_file(f.url)
        if not data:
            continue
        mimetype = f.mimetype or "image/png"
        out.append(f"data:{mimetype};base64,{base64.b64encode(data).decode('ascii')}")
    return out


def register(app, runtime: Runtime):
    settings = runtime.settings

    @app.event("channel_created")
    def handle_channel_created_event(ack, event, client):
        ack()
        slack = runtime.slack_client(client)
        try:
            announce_new_channel_created(
                ChannelCreatedEvent.from_payload(event),
                slack,
                freetalk_channel=settings.FREETALK_CHANNEL_ID,
            )
        except Exception as exc:
            report_failure(slack, settings.ADMIN_CHANNEL, event, exc)

    @app.event("message")
    def handle_message_event(ack, event, client):
        ack()
        # 수정은 새 글이 아니다 (자동 답글 대상 채널은 수정이 잦아 DEBUG 로만 남긴다)
        if is_edited_message(event):
            logger.debug("Ignoring edited message event (ts=%s)", event.get("ts"))
            return
        slack = runtime.slack_client(client)
        try:
            subin_like_response(
                MessageEvent.from_payload(event),
                slack,
                runtime.qa(),
                anna_id=settings.ANNA_ID,
                channel_id=settings.AUTO_REPLY_CHANNEL_ID,
            )
        except Exception as exc:
            report_failure(slack, settings.ADMIN_CHANNEL, event, exc)
