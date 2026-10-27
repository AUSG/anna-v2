import unittest
from unittest.mock import patch

from shared.retry import retry
from shared.text import strip_multiline


class TestStripMultiline(unittest.TestCase):
    def test_singleline(self):
        sample = "hello world"
        assert strip_multiline(sample, ignore_first_line=False) == sample

    def test_multiline(self):
        sample = """
        <@ABCDE12345> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
        ```
        핸드폰: "010-1234-5678
        이메일: "abcde@gmail.com"
        학교/회사: "siwon school"
        ```
        (참고로 이 메시지는 너만 볼 수 있어!)"""
        assert (
            strip_multiline(sample)
            == """<@ABCDE12345> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
```
핸드폰: "010-1234-5678
이메일: "abcde@gmail.com"
학교/회사: "siwon school"
```
(참고로 이 메시지는 너만 볼 수 있어!)"""
        )

    def test_multiline_with_various_blanks(self):
        sample = """
        A
            B
    C"""
        assert (
            strip_multiline(sample)
            == """    A
        B
C"""
        )

    def test_multiline_with_first_line(self):
        sample = """hello
        A
            B
    C"""
        assert (
            strip_multiline(sample, ignore_first_line=False)
            == """hello
        A
            B
    C"""
        )

    def test_multiline_with_arguments(self):
        sample = """
        hello
        {}
        B
        {}"""
        assert (
            strip_multiline(sample, "A", "CCC")
            == """hello
A
B
CCC"""
        )


@patch("shared.retry.time.sleep")
class TestRetry(unittest.TestCase):
    def test_retry_success(self, mock_sleep):
        attempts = 0

        def always_succeed():
            nonlocal attempts
            attempts += 1
            return "success"

        self.assertEqual(retry(always_succeed, wait_sec=0.01), "success")
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_retry_failure(self, mock_sleep):
        attempts = 0

        def always_fail():
            nonlocal attempts
            attempts += 1
            raise ValueError("failure")

        with self.assertRaises(ValueError):
            retry(always_fail, wait_sec=0.01)
        self.assertEqual(attempts, 10)
        self.assertEqual(mock_sleep.call_count, 10)
        mock_sleep.assert_called_with(0.01)

    def test_retry_honours_attempts(self, mock_sleep):
        attempts = 0

        def always_fail():
            nonlocal attempts
            attempts += 1
            raise ValueError("failure")

        with self.assertRaises(ValueError):
            retry(always_fail, attempts=3, wait_sec=0.01)
        self.assertEqual(attempts, 3)

    def test_retry_non_retryable_exception_raises_immediately(self, mock_sleep):
        attempts = 0

        def always_fail_with_non_retryable():
            nonlocal attempts
            attempts += 1
            raise KeyError("failure")

        with self.assertRaises(KeyError):
            retry(
                always_fail_with_non_retryable,
                wait_sec=0.01,
                non_retryable=(KeyError,),
            )
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_retry_partial_success(self, mock_sleep):
        attempts = 0

        def succeed_after_two_attempts():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("failure")
            return "success"

        self.assertEqual(retry(succeed_after_two_attempts, wait_sec=0.01), "success")
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.call_count, 2)
