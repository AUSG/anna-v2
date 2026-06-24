import base64
import json
import unittest

from implementation.arp_otp import ArpOtp


def decode_base64url(value):
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


class TestArpOtp(unittest.TestCase):
    def test_issue_code(self):
        sut = ArpOtp(
            base_url="https://arp.ausg.me/",
            secret="test-secret",
            now=lambda: 1000,
        )

        code = sut.issue_code("U123")
        payload_part, signature = code.split(".")

        payload = json.loads(decode_base64url(payload_part))
        assert payload == {
            "exp": 1600,
            "purpose": "arp-login-v1",
            "sub": "U123",
        }
        assert len(signature) > 0

    def test_issue_login_url(self):
        sut = ArpOtp(
            base_url="https://arp.ausg.me/",
            secret="test-secret",
            now=lambda: 1000,
        )

        login_url = sut.issue_login_url("U123")

        assert login_url.startswith("https://arp.ausg.me/auth/otp?code=")

    def test_require_base_url_and_secret(self):
        with self.assertRaises(ValueError):
            ArpOtp(base_url="", secret="test-secret").issue_code("U123")

        with self.assertRaises(ValueError):
            ArpOtp(base_url="https://arp.ausg.me", secret="").issue_code("U123")
