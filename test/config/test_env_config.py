import os
import unittest
from unittest.mock import patch

from config.env_config import Settings


class TestSettings(unittest.TestCase):
    def test_reads_environment_variables(self):
        with patch.dict(os.environ, {"LOGLEVEL": "TEST_VALUE"}):
            assert Settings().LOGLEVEL == "TEST_VALUE"

    def test_each_instance_reads_the_environment_at_construction(self):
        # 전역 싱글톤이 아니라 bootstrap 이 만들 때마다 환경을 읽는다
        with patch.dict(os.environ, {"ANNA_ID": "UFIRST"}):
            first = Settings()
        with patch.dict(os.environ, {"ANNA_ID": "USECOND"}):
            second = Settings()

        assert first.ANNA_ID == "UFIRST"
        assert second.ANNA_ID == "USECOND"

    def test_gcp_service_account_restores_private_key_newlines(self):
        with patch.dict(
            os.environ,
            {
                "GCP_type": "service_account",
                "GCP_private_key": "-----BEGIN\\nabc\\n-----END",
                "GCP_client_email": "anna@example.iam.gserviceaccount.com",
            },
        ):
            account = Settings().gcp_service_account()

        assert account["type"] == "service_account"
        assert account["private_key"] == "-----BEGIN\nabc\n-----END"
        assert account["client_email"] == "anna@example.iam.gserviceaccount.com"
