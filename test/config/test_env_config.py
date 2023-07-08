import os
import unittest


class TestEnvConfig(unittest.TestCase):
    def test_init_envs(self):
        os.environ["LOGLEVEL"] = "TEST_VALUE"
        from config.env_config import envs
        assert envs.LOGLEVEL == "TEST_VALUE"
