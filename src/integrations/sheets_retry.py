"""Shared Sheets retry policy; writes require an explicit confirmation step."""

import time

from google.auth.exceptions import TransportError
from gspread.exceptions import APIError
from requests.exceptions import ConnectionError, RequestException, Timeout
from tenacity import RetryCallState, Retrying, retry_if_exception

TRANSPORT_ERRORS = (APIError, RequestException, TransportError)
_RETRY_DELAYS = (1, 2)
_RATE_LIMIT_DELAYS = (5, 10, 20, 30)


def status(error):
    return getattr(getattr(error, "response", None), "status_code", None)


def _transient(error):
    return isinstance(error, (ConnectionError, Timeout, TransportError)) or status(
        error
    ) in (
        408,
        429,
        500,
        502,
        503,
        504,
    )


def _delays(state: RetryCallState):
    assert state.outcome is not None
    return (
        _RATE_LIMIT_DELAYS
        if status(state.outcome.exception()) == 429
        else _RETRY_DELAYS
    )


def _wait(state: RetryCallState):
    delays = _delays(state)
    return delays[min(state.attempt_number - 1, len(delays) - 1)]


def _stop(state: RetryCallState):
    return state.attempt_number > len(_delays(state))


def _policy():
    return Retrying(
        retry=retry_if_exception(_transient),
        wait=_wait,
        stop=_stop,
        sleep=lambda seconds: time.sleep(seconds),
        reraise=True,
    )


def retry_reads(method):
    """Own retries at the public read boundary, never at its inner helpers."""
    return _policy().wraps(method)


def guarded_write(send, *, confirmed):
    """Reconcile a failed write before Tenacity may replay its guarded request.

    Confirmation runs outside the attempt context. If it fails, its exception
    escapes instead of being mistaken for another retryable write failure.
    Atomic unique IDs or revision filters must guard every caller's write.
    """
    for attempt in _policy():
        with attempt:
            send()
        outcome = attempt.retry_state.outcome
        assert outcome is not None
        if not outcome.failed:
            return
        if not isinstance(outcome.exception(), TRANSPORT_ERRORS):
            outcome.result()
        if confirmed():
            return
