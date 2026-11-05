"""Apply the operation deadline at every Sheets and credential HTTP send."""

from google.auth.transport.requests import AuthorizedSession, Request
from gspread.http_client import HTTPClient
from requests import Session
from urllib3.util import Timeout

from integrations.sheets_retry import remaining_seconds

REQUEST_TIMEOUT = (5, 20)


class _DeadlineTransport(Session):
    def send(self, request, **kwargs):
        remaining = remaining_seconds()
        if remaining is not None:
            # urllib3 deducts connection time from total before reading. Each
            # send (including redirects/auth refresh) computes the budget anew.
            kwargs["timeout"] = Timeout(
                total=remaining, connect=REQUEST_TIMEOUT[0], read=REQUEST_TIMEOUT[1]
            )
        # A response that already arrived is returned even if the deadline passed
        # meanwhile; the next send is refused before it reaches the network.
        return super().send(request, **kwargs)


class _SheetsSession(_DeadlineTransport, AuthorizedSession):
    def __init__(self, auth):
        self._credential_session = _DeadlineTransport()
        super().__init__(auth, auth_request=Request(self._credential_session))

    def close(self):
        self._credential_session.close()
        super().close()


class SheetsHTTPClient(HTTPClient):
    def __init__(self, auth, session=None):
        super().__init__(
            auth, session=session if session is not None else _SheetsSession(auth)
        )
        self.auth = auth
