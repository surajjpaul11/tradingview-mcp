"""
Free-port discovery so several copies of the app (e.g. one per git worktree)
can run side by side without colliding on 8000.

`reserve_port()` is the preferred entry point for a server that is about to start:
it binds and holds the socket, so nothing can take the port between the check and
the listen. `find_free_port()` / `resolve_port()` only probe, which leaves a small
race, and exist for callers that cannot accept a pre-bound socket (the CLI, and
FastMCP's streamable-http transport, which opens its own socket).

A port counts as free only if BOTH checks pass:
  1. nothing accepts a TCP connection on 127.0.0.1:<port> (catches servers bound
     to any address, including Docker port mappings on the host), and
  2. we can bind <host>:<port> ourselves (catches ports reserved but not listening).

There is a small window between the check and the real server binding; if another
process grabs the port in that window the server will fail loudly on startup.

CLI (used by start.command):
  python -m tradingview_mcp.core.utils.ports                 # prints first free port from 8000
  python -m tradingview_mcp.core.utils.ports --start 8100 --max-tries 5 --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import errno
import os
import socket
import sys

DEFAULT_START_PORT = 8000
DEFAULT_MAX_TRIES = 50


def reserve_port(host: str, preferred_port: int, attempts: int = DEFAULT_MAX_TRIES) -> socket.socket:
    """
    Bind and hold the first available port from `preferred_port`, returning the listening
    socket. Pass it to the server (e.g. uvicorn `sockets=[sock]`) so no other process can
    claim the port in between. `preferred_port=0` lets the OS choose any free port.
    """
    if not 0 <= preferred_port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    ports = [0] if preferred_port == 0 else range(preferred_port, min(preferred_port + attempts, 65536))
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(socket.SOMAXCONN)
            return sock
        except OSError as exc:
            sock.close()
            if exc.errno != errno.EADDRINUSE:
                raise
    raise OSError(f"No free port found starting at {preferred_port}")


def _accepts_connections(port: int, timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # No SO_REUSEADDR: we want bind() to fail if anything holds the port.
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """True if nothing is listening on the port and we can bind it on `host`."""
    return not _accepts_connections(port) and _can_bind(host, port)


def find_free_port(start: int = DEFAULT_START_PORT, host: str = "127.0.0.1",
                   max_tries: int = DEFAULT_MAX_TRIES) -> int:
    """Return the first free port in [start, start + max_tries). Raises RuntimeError if none."""
    for port in range(start, min(start + max_tries, 65536)):
        if is_port_free(port, host):
            return port
    raise RuntimeError(f"No free port in {start}-{start + max_tries - 1} on {host}")


def resolve_port(requested: int | None = None, host: str = "127.0.0.1", strict: bool | None = None) -> int:
    """
    Pick the port a server should bind.

    requested: preferred port (default: $PORT or 8000).
    strict:    if True, use `requested` exactly and fail if busy (default: $PORT_STRICT == "1").
               Otherwise scan upward for the first free port ($PORT_MAX_TRIES, default 50).
    """
    if requested is None:
        requested = int(os.environ.get("PORT", DEFAULT_START_PORT))
    if strict is None:
        strict = os.environ.get("PORT_STRICT", "0") == "1"
    if strict:
        if not is_port_free(requested, host):
            raise RuntimeError(f"Port {requested} on {host} is in use (PORT_STRICT=1)")
        return requested
    max_tries = int(os.environ.get("PORT_MAX_TRIES", DEFAULT_MAX_TRIES))
    port = find_free_port(requested, host, max_tries)
    if port != requested:
        print(f"[ports] Port {requested} is busy — using {port} instead.", file=sys.stderr, flush=True)
    return port


def main() -> None:
    ap = argparse.ArgumentParser(description="Print the first free TCP port.")
    ap.add_argument("--start", type=int, default=int(os.environ.get("PORT", DEFAULT_START_PORT)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--max-tries", type=int, default=int(os.environ.get("PORT_MAX_TRIES", DEFAULT_MAX_TRIES)))
    args = ap.parse_args()
    try:
        print(find_free_port(args.start, args.host, args.max_tries))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
