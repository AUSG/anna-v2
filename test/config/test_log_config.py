import unittest


class TestLogConfig(unittest.TestCase):
    def test_init_logger(self):
        with self.assertLogs() as cm:  # context manager
            from config.log_config import init_logger
            init_logger()
            self.assertTrue("log config initialized" in cm.output[0])

    def test_get_logger(self):
        with self.assertLogs() as cm:  # context manager
            from config.log_config import get_logger
            get_logger().info("test")
            self.assertTrue("test_log_config" in cm.output[0])
