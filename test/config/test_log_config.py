import logging
import unittest
from importlib import reload
from unittest.mock import patch

from config import log_config


class TestLogConfig(unittest.TestCase):
    def test_init_logger(self):
        with self.assertLogs() as cm:  # context manager
            reload(log_config)
            log_config.init_logger()
            self.assertTrue("log config initialized" in cm.output[0])

    def test_get_logger(self):
        with self.assertLogs() as cm:  # context manager
            reload(log_config)
            logging.getLogger(__name__).info("test")
            self.assertTrue("test_log_config" in cm.output[0])
