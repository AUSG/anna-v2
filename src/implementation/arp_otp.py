import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


class ArpOtp:
    PURPOSE = "arp-login-v1"
    TTL_SECONDS = 10 * 60

    def __init__(self, base_url: str, secret: str, now=None):
        self.base_url = (base_url or "").rstrip("/")
        self.secret = secret or ""
        self.now = now or time.time

    def issue_login_url(self, slack_user_id: str) -> str:
        code = self.issue_code(slack_user_id)
        return f"{self.base_url}/auth/otp?{urlencode({'code': code})}"

    def issue_code(self, slack_user_id: str) -> str:
        if not self.base_url:
            raise ValueError("ARP_BASE_URL is required")
        if not self.secret:
            raise ValueError("ARP_OTP_SECRET is required")
        if not slack_user_id:
            raise ValueError("slack_user_id is required")

        payload = {
            "exp": int(self.now()) + self.TTL_SECONDS,
            "purpose": self.PURPOSE,
            "sub": slack_user_id,
        }
        payload_part = self._base64url(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = self._base64url(
            hmac.new(
                self.secret.encode("utf-8"),
                payload_part.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        return f"{payload_part}.{signature}"

    @staticmethod
    def _base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")
