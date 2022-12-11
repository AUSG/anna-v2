from _pytest.python_api import raises

from service.qna.qna_service import _find_keyword


# add_dummy_envs()


def test_fail_when_keyword_prefix_is_None():
    with raises(TypeError):
        _find_keyword(None, '!random string')


def test_fail_when_text_is_None():
    assert _find_keyword('!', None) is None


def test_fail_when_keyword_prefix_not_in_text():
    assert _find_keyword('!', 'random string') is None


def test_fail_when_keyword_prefix_on_last_position_in_text():
    assert _find_keyword('!', 'random string!') is None


def test_fail_keyword_is_only_spaces():
    assert _find_keyword('!', '!          ') is None


def test_success_with_one_length_keyword_prefix():
    assert _find_keyword('!', 'string!random hello') == 'random'


def test_success_with_two_length_keyword_prefix():
    assert _find_keyword('!!', 'str!!ingrandom hello') == 'ingrandom'


def test_success_with_keyword_prefix_in_two_position():
    assert _find_keyword('!', 'str!ing!random h!ello') == 'ing'


def test_success_with_two_length_keyword_prefix_in_two_position():
    assert _find_keyword('!!', 'str!!ingrand!!om he!!llo') == 'ingrand'
