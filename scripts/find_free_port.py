#!/usr/bin/env python3
"""Print a free TCP port, preferring one if it is available.

Used by the Makefile so ``make run`` never dies with "address already in use":
it tries the requested port first and only falls back to an OS-assigned free
port when that one is taken. Prints a single integer to stdout.

Usage:
    python scripts/find_free_port.py [preferred_port] [host]
"""
from __future__ import annotations

import socket
import sys


def _is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(preferred: int, host: str = "127.0.0.1") -> int:
    if preferred and _is_free(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def main() -> int:
    preferred = 0
    host = "127.0.0.1"
    if len(sys.argv) > 1:
        try:
            preferred = int(sys.argv[1])
        except ValueError:
            preferred = 0
    if len(sys.argv) > 2:
        host = sys.argv[2]
    print(find_free_port(preferred, host))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
