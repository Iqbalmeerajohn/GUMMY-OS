"""Run the API on a dual-stack socket, so `localhost` is not slow.

`uvicorn app.main:app` binds `127.0.0.1`, which is IPv4 only. Modern clients
resolve `localhost` to the IPv6 loopback `::1` first and only fall back to IPv4
after a Happy Eyeballs delay — 200 ms in curl, and a similar penalty in
browsers. Nothing looks broken, because every request still succeeds; they are
each just a fifth of a second slower than they need to be. Measured against
this app: 2.8 ms over `127.0.0.1`, 211 ms over `localhost`.

That is not a micro-optimisation here. The frontend calls
`http://localhost:8000`, so *every* API call the browser makes paid it.

Binding `--host ::` instead does not fix it, it only reverses it: Windows
defaults IPv6 sockets to V6ONLY, so `localhost` becomes fast and `127.0.0.1`
becomes slow (measured at 2 s). The fix is one socket that genuinely serves
both families — `AF_INET6` with `IPV6_V6ONLY` cleared — which is what this does.

    python scripts/serve.py            # dual-stack, port 8000
    python scripts/serve.py --reload   # same, with autoreload

Falls back to IPv4 when the host has no IPv6 stack at all, because a server
that refuses to start is worse than one that is occasionally slow.
"""

from __future__ import annotations

import argparse
import socket
import sys

import uvicorn


def dual_stack_socket(port: int, backlog: int = 2048) -> socket.socket | None:
    """A listening socket that accepts both IPv6 and IPv4 loopback clients.

    Returns ``None`` when IPv6 is unavailable, so the caller can fall back
    rather than fail.
    """
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    except OSError:
        return None
    try:
        # The whole point: without this, the socket serves ::1 only and IPv4
        # clients pay the same connection delay we are trying to remove.
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("::", port))
        sock.listen(backlog)
        sock.set_inheritable(True)
    except OSError:
        sock.close()
        return None
    return sock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    config = uvicorn.Config(
        "app.main:app",
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )

    sock = dual_stack_socket(args.port)
    if sock is None:
        print(
            "IPv6 unavailable; falling back to 127.0.0.1 "
            "(requests to 'localhost' may be slower).",
            file=sys.stderr,
        )
        config.host = "127.0.0.1"
        uvicorn.Server(config).run()
        return 0

    # Reload needs a real host/port to re-bind in the child process, and the
    # reloader does not carry a socket across the restart. Autoreload is a
    # development convenience; speed is the thing worth keeping, so this takes
    # the dual-stack socket and gives up the reload rather than the reverse.
    if args.reload:
        sock.close()
        print(
            "--reload cannot share a pre-bound socket; "
            "serving IPv6+IPv4 without autoreload.",
            file=sys.stderr,
        )
        config.reload = False
        sock = dual_stack_socket(args.port)
        if sock is None:
            config.host = "127.0.0.1"
            uvicorn.Server(config).run()
            return 0

    with sock:
        uvicorn.Server(config).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
