import socket

import pytest

from lookout.offline import OfflineViolation, offline


def test_non_local_connection_is_blocked():
    with offline():
        with pytest.raises(OfflineViolation):
            socket.create_connection(("10.255.255.1", 80), timeout=1)


def test_hostname_connection_is_blocked():
    with offline():
        s = socket.socket()
        try:
            with pytest.raises(OfflineViolation):
                s.connect(("example.com", 80))
        finally:
            s.close()


def test_loopback_is_allowed():
    """The local model server is on loopback; reaching it must still work."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        with offline():
            client = socket.create_connection(server.getsockname(), timeout=2)
            client.close()
    finally:
        server.close()


def test_guard_is_removed_afterwards():
    real = socket.socket.connect
    with offline():
        assert socket.socket.connect is not real
    assert socket.socket.connect is real


def test_nested_guards_hold_until_the_last_one_exits():
    """Two days processed at once: the first to finish must not lift the guard."""
    real = socket.socket.connect
    with offline():
        with offline():
            pass
        assert socket.socket.connect is not real
        with pytest.raises(OfflineViolation):
            socket.create_connection(("10.255.255.1", 80), timeout=1)
    assert socket.socket.connect is real
