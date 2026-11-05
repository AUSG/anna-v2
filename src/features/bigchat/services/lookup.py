"""빅챗 모집글 판별. 일반 대화의 :gogo:에는 Sheets 장애 중에도 안내하지 않는다."""

import logging
import re

from features.bigchat.errors import BigchatStorageError

logger = logging.getLogger(__name__)


def find_bigchat(slack_client, bigchats, *, channel: str, ts: str) -> int | None:
    """ts 글에 연결된 신청 시트 ID를 돌려준다. 빅챗 모집글이 아니면 None.

    일반 대화에서도 :gogo:를 자주 쓰므로, 모집글이 아닌 글이나 댓글에는 아무 안내도 하지 않는다.
    Sheets를 읽지 못하면 모집글인지 알 수 없다. 이때는 봇이 이 글에 올린 시트 링크가 스레드에
    있을 때만 오류를 다시 던져서, 호출한 핸들러가 다른 오류처럼 안내하게 한다.
    """
    try:
        return bigchats.find(channel=channel, thread_ts=ts)
    except BigchatStorageError:
        logger.warning(
            "Failed to look up the bigchat of %s/%s", channel, ts, exc_info=True
        )
        if _has_posted_sheet_link(slack_client, bigchats, channel, ts):
            raise
        return None


def _has_posted_sheet_link(slack_client, bigchats, channel, ts) -> bool:
    # 시트 ID는 모집글(channel, ts)로 정해지므로 Sheets 없이도 봇이 올린 링크를 알 수 있다.
    # 다른 글의 링크나, 이 링크 뒤에 숫자가 더 붙은 링크는 이 모집글로 보지 않는다.
    link = re.compile(
        re.escape(bigchats.sheet_url(channel=channel, thread_ts=ts)) + r"(?!\d)"
    )
    try:
        messages = slack_client.get_replies(channel=channel, thread_ts=ts)
    except Exception:
        # 안내 여부만 정하는 보조 확인이다. 스레드를 읽지 못하면 일반 글로 보고 넘어간다.
        logger.warning("Failed to read the thread of %s/%s", channel, ts, exc_info=True)
        return False
    return any(link.search(message.text) for message in messages)
