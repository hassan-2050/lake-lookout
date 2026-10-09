"""Enforce "nothing leaves this computer" while a day is being processed.

Every outgoing connection is checked, and anything that is not loopback raises
instead of connecting. The local Ollama server is on 127.0.0.1, so the model
still works; a stray download, a telemetry call, or an OLLAMA_HOST pointing at
someone else's server fails loudly rather than quietly sending a hiker's photos
and locations away.

This guards connections, not socket creation. Some library imports build
sockets without connecting, so blocking construction would break unrelated
imports.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
from contextlib import contextmanager

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


class OfflineViolation(ConnectionError):
    """Something tried to reach a non-local address during processing."""


def _is_local(address) -> bool:
    if not isinstance(address, tuple):      # AF_UNIX path
        return True
    host = address[0]
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False                         # a hostname: would need DNS, so not local


def _guarded_connect(self, address):
    if not _is_local(address):
        raise OfflineViolation(f"blocked connection to {address!r}: Lake Lookout "
                               "runs offline and only talks to the local model")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_local(address):
        raise OfflineViolation(f"blocked connection to {address!r}")
    return _real_connect_ex(self, address)


_lock = threading.Lock()
_depth = 0


@contextmanager
def offline():
    """Block every non-loopback connection inside the `with` block.

    Reference-counted: the app can process two days at once in separate
    threads, and the first to finish must not lift the guard from the other.
    """
    global _depth
    with _lock:
        _depth += 1
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
    try:
        yield
    finally:
        with _lock:
            _depth -= 1
            if _depth == 0:
                socket.socket.connect = _real_connect
                socket.socket.connect_ex = _real_connect_ex
