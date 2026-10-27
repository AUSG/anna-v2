"""테스트 중 실서비스로 연결되는 소켓을 차단한다."""

import socket

import pytest


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not contact external services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
