import logging

logger = logging.getLogger(__name__)

EMOJI_NAME = "loading"


class LoadingEmoji:
    """실제 처리를 시작하는 시점에 loading 이모지를 붙이고, 블록을 벗어나면 뗀다.

    핸들러 바깥(데코레이터)에서 붙이면 아무 동작도 하지 않는 이벤트(빅챗 글이 아닌 메시지에
    이모지가 달린 경우 등)에도 이모지가 붙었다 떨어진다. 그래서 이모지를 붙일지 말지는
    핸들러가 정하도록 컨텍스트 매니저로 주입하고, 핸들러는 실제로 뭔가 하기로 결정한
    지점에서만 with 블록에 들어간다.

    이모지 추가/삭제는 부가 기능이므로 실패해도 본 작업을 막지 않고 로그만 남긴다.
    붙이지 못했으면 떼려고도 하지 않는다. 특히 삭제 실패를 그냥 올려보내면 본 작업이
    남긴 예외를 덮어써 원인을 잃어버린다.
    """

    def __init__(self, slack_client, channel, ts):
        self.slack_client = slack_client
        self.channel = channel
        self.ts = ts
        self._added = False

    def __enter__(self):
        if not self.channel or not self.ts:
            return self
        try:
            self.slack_client.add_emoji(self.channel, self.ts, EMOJI_NAME)
            self._added = True
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to add loading emoji: %s", ex)
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._added:
            return False
        self._added = False
        try:
            self.slack_client.remove_emoji(self.channel, self.ts, EMOJI_NAME)
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to remove loading emoji: %s", ex)
        return False
