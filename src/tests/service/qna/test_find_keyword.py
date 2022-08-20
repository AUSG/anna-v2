from _pytest.python_api import raises

from tests.util import add_dummy_envs

add_dummy_envs()

from service.qna.qna_service import find_keyword


def test_fail_when_keyword_prefix_is_None():
    with raises(TypeError):
        find_keyword(None, '!random string')


def test_fail_when_text_is_None():
    assert find_keyword('!', None) is None


def test_fail_when_keyword_prefix_not_in_text():
    assert find_keyword('!', 'random string') is None


def test_fail_when_keyword_prefix_on_last_position_in_text():
    assert find_keyword('!', 'random string!') is None


def test_fail_keyword_is_only_spaces():
    assert find_keyword('!', '!          ') is None


def test_success_with_one_length_keyword_prefix():
    assert find_keyword('!', 'string!random hello') == 'random'


def test_success_with_two_length_keyword_prefix():
    assert find_keyword('!!', 'str!!ingrandom hello') == 'ingrandom'


def test_success_with_keyword_prefix_in_two_position():
    assert find_keyword('!', 'str!ing!random h!ello') == 'ing'


def test_success_with_two_length_keyword_prefix_in_two_position():
    assert find_keyword('!!', 'str!!ingrand!!om he!!llo') == 'ingrand'
