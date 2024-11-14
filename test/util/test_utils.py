import unittest

from util.utils import search_value, strip_multiline, with_retry


class TestUtils(unittest.TestCase):
    def test_find_str(self):
        sample = {
            "key": "value"
        }
        assert search_value(sample, "key") == "value"

    def test_find_dict(self):
        sample = {
            "key": {
                "sub_key": "sub_value"
            }
        }
        assert search_value(sample, "key")["sub_key"] == "sub_value"

    def test_find_nested_dict(self):
        sample = {
            "key": {
                "sub_key": {
                    "sub_sub_key" : "sub_sub_value"
                }
            }
        }
        assert search_value(sample, "sub_key")["sub_sub_key"] == "sub_sub_value"

    def test_find_list(self):
        sample = {
            "key": ["a", "b", "c"]
        }
        assert search_value(sample, "key")[1] == "b"

    def test_find_nested_list(self):
        sample = {
            "key":{
                "sub_key": ["a", "b", "c"]
            }
        }
        assert search_value(sample, "sub_key")[0] == "a"
        assert search_value(sample, "sub_key")[1] == "b"
        assert search_value(sample, "sub_key")[2] == "c"

    def test_find_deep_nested_list(self):
        sample = {
            "key":{
                "sub_key": ["a", {"sub_sub_key" : ["aa", "bb", "cc"]}, "c"]
            }
        }
        assert search_value(sample, "sub_sub_key")[0] == "aa"
        assert search_value(sample, "sub_sub_key")[1] == "bb"
        assert search_value(sample, "sub_sub_key")[2] == "cc"


    def test_find_fail(self):
        sample = {}
        assert search_value(sample, "key") is None


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
        assert strip_multiline(sample) == """<@ABCDE12345> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
```
핸드폰: "010-1234-5678
이메일: "abcde@gmail.com"
학교/회사: "siwon school"
```
(참고로 이 메시지는 너만 볼 수 있어!)"""

    def test_multiline_with_various_blanks(self):
        sample = """
        A
            B
    C"""
        assert strip_multiline(sample) == """    A
        B
C"""

    def test_multiline_with_first_line(self):
        sample = """hello
        A
            B
    C"""
        assert strip_multiline(sample, ignore_first_line=False) == """hello
        A
            B
    C"""

    def test_multiline_with_arguments(self):
        sample = """
        hello
        {}
        B
        {}"""
        assert strip_multiline(sample,"A", "CCC") == """hello
A
B
CCC"""

class TestWithRetry(unittest.TestCase):
    def test_with_retry_success(self):
        attempts=0

        @with_retry(fixed_wait_time_in_sec=0.01)
        def always_succeed():
            nonlocal attempts
            attempts+=1
            return "success"

        self.assertEqual(always_succeed(), "success")
        self.assertEqual(attempts, 1)

    def test_with_retry_failure(self):
        attempts = 0

        @with_retry(fixed_wait_time_in_sec=0.01)
        def always_fail():
            nonlocal attempts
            attempts+=1
            raise ValueError("failure")

        with self.assertRaises(ValueError):
            always_fail()
        self.assertEqual(attempts, 10)

    def test_with_retry_partial_success(self):
        attempts = 0

        @with_retry(fixed_wait_time_in_sec=0.01)
        def succeed_after_two_attempts():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("failure")
            return "success"

        self.assertEqual(succeed_after_two_attempts(), "success")
        self.assertEqual(attempts, 3)
