from tests.util import enable_dummy_envs

# TODO : 다음 조건 만족 시 제거
#  env 깡으로 박아둔 것 때문에 아래 파일들 import 시 env error 발생. env 불러오는 코드를 한 파일로 물리적으로 응집하고 테스트 환경을 위한 기본값 넣기
enable_dummy_envs()

from unittest import TestCase


class OfflineMeetingParticipationServiceTest(TestCase):
    pass