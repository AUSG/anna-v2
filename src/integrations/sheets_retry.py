"""Shared Sheets retry policy; writes require an explicit confirmation step."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from google.auth.exceptions import TransportError
from gspread.exceptions import APIError
from requests.exceptions import ConnectionError, RequestException, Timeout
from tenacity import RetryCallState, Retrying, retry_if_exception

TRANSPORT_ERRORS = (APIError, RequestException, TransportError)
_RETRY_DELAYS = (1, 2)
_RATE_LIMIT_DELAYS = (5, 10, 20, 30)
OPERATION_SECONDS = 90
_deadline: ContextVar[float | None] = ContextVar("sheets_deadline", default=None)


class OperationTimeout(Timeout):
    pass


def remaining_seconds():
    deadline = _deadline.get()
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OperationTimeout("Sheets operation exhausted its time budget")
    return remaining


@contextmanager
def operation_budget():
    """Bound when new Sheets work may start; finished work is never discarded.

    Checking again after success would report a committed write as unconfirmed.
    """
    token = None
    if _deadline.get() is None:
        token = _deadline.set(time.monotonic() + OPERATION_SECONDS)
    try:
        remaining_seconds()
        yield
    finally:
        if token is not None:
            _deadline.reset(token)


@contextmanager
def write_lock(lock):
    remaining = remaining_seconds()
    acquired = (
        lock.acquire(timeout=remaining) if remaining is not None else lock.acquire()
    )
    if not acquired:
        raise OperationTimeout("Timed out waiting for the Sheets write lock")
    try:
        remaining_seconds()
        yield
    finally:
        lock.release()


def status(error):
    return getattr(getattr(error, "response", None), "status_code", None)


def _transient(error):
    if isinstance(error, OperationTimeout):
        return False
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
    if state.attempt_number > len(_delays(state)):
        return True
    remaining = remaining_seconds()
    return remaining is not None and state.upcoming_sleep >= remaining


def _check_budget(_state: RetryCallState):
    remaining_seconds()


def _policy():
    return Retrying(
        before=_check_budget,
        retry=retry_if_exception(_transient),
        wait=_wait,
        stop=_stop,
        sleep=lambda seconds: time.sleep(seconds),
        reraise=True,
    )


def retry_reads(method):
    """Own retries at the public read boundary, never at its inner helpers."""

    @wraps(method)
    def invoke(*args, **kwargs):
        with operation_budget():
            return _policy()(method, *args, **kwargs)

    return invoke


def guarded_write(send, *, confirmed):
    """Reconcile a failed write before Tenacity may replay its guarded request.

    Confirmation runs outside the attempt context. If it fails, its exception
    escapes instead of being mistaken for another retryable write failure.
    Atomic unique IDs or revision filters must guard every caller's write.
    """
    with operation_budget():
        for attempt in _policy():
            with attempt:
                send()
            outcome = attempt.retry_state.outcome
            assert outcome is not None
            if not outcome.failed:
                return
            if not isinstance(outcome.exception(), TRANSPORT_ERRORS):
                outcome.result()
            remaining_seconds()
            if confirmed():
                return
