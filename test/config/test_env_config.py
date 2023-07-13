import os
import unittest
from importlib import reload
from config import env_config

class TestEnvConfig(unittest.TestCase):
    def test_init_envs(self):
        os.environ["LOGLEVEL"] = "TEST_VALUE"
        reload(env_config)
        assert env_config.envs.LOGLEVEL == "TEST_VALUE"
