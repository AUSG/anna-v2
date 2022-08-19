from service.qna.qna_service import find_reply


def test_none_when_keyword_None():
    assert find_reply(None) is None


def test_none_when_keyword_not_registered():
    assert find_reply("random_keyword_12345") is None


def test_success_with_keyword_wifi():
    assert find_reply('wifi') == '센터필드의 와이파이를 알려줄게. 이름은 `Guest`, 비밀번호는 `BrokenWires@@2019`야!'
