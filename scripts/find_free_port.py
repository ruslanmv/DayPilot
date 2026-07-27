#!/usr/bin/env python3
"""Print a free TCP port, preferring one and then the next ones in sequence.

Used by the Makefile so ``make start`` / ``make run`` never die with "address
already in use": it tries the requested port first, then the next ports in order
(8080 → 8081 → 8082 …), and only falls back to an OS-assigned free port if a
whole window of sequential ports is taken. Prints a single integer to stdout.

Usage:
    python scripts/find_free_port.py [preferred_port] [host] [max_scan]
"""
from __future__ import annotations

import socket
import sys

_MAX_PORT = 65535
DEFAULT_SCAN = 64


def _is_free(host: str, port: int) -> bool:
    # Mirror uvicorn's own bind (asyncio sets SO_REUSEADDR on Unix): an active
    # listener is still reported busy, while a port merely in TIME_WAIT — which
    # uvicorn can reuse — is not needlessly skipped on a quick restart.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(preferred: int, host: str = "127.0.0.1", max_scan: int = DEFAULT_SCAN) -> int:
    """Return ``preferred`` if free, else the next free port after it (scanning up
    to ``max_scan`` ports), else any OS-assigned free port."""
    if preferred:
        for port in range(preferred, min(preferred + max(1, max_scan), _MAX_PORT + 1)):
            if _is_free(host, port):
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _int_arg(index: int, default: int) -> int:
    if len(sys.argv) > index:
        try:
            return int(sys.argv[index])
        except ValueError:
            return default
    return default


def main() -> int:
    preferred = _int_arg(1, 0)
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    max_scan = _int_arg(3, DEFAULT_SCAN)
    print(find_free_port(preferred, host, max_scan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
