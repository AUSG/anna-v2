from service.qna.qna_service import is_message_sent_event


def _get_sample_event():
    return {
        'type': 'message',
        'thread_ts': 111,
        'ts': 222,
        'text': '!hello'
    }


def test_false_when_subtype_is_not_None():
    event = _get_sample_event()
    event['subtype'] = 'message_deleted'
    assert is_message_sent_event(event) is False


def test_false_when_type_is_not_message():
    event1 = _get_sample_event()
    event1['type'] = 'reply'

    assert is_message_sent_event(event1) is False


def test_false_when_type_is_None():
    event = _get_sample_event()
    del event['type']

    assert is_message_sent_event(event) is False


def test_true():
    event = _get_sample_event()

    assert is_message_sent_event(event) is True
