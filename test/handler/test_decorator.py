import unittest
from unittest.mock import MagicMock

from handler.decorator import catch_global_error


class TestCatchGlobalError(unittest.TestCase):
    def test_error_messages_disable_unfurling(self):
        """에러 알림(어드민 채널 / 사용자 안내)에도 미리보기가 붙지 않아야 한다."""

        def boom(**kwargs):
            raise RuntimeError("boom")

        mock_say = MagicMock()
        event = {"channel": "C03SZTDEDK3", "ts": "1689437594.220999"}
        sut = catch_global_error()(boom)

        sut(client=MagicMock(), event=event, say=mock_say)

        assert mock_say.call_count == 2
        for call in mock_say.call_args_list:
            assert call.kwargs["unfurl_links"] is False
            assert call.kwargs["unfurl_media"] is False
