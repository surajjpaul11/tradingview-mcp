"""Launch the dashboard alongside other local copies of the project."""

import argparse
import errno
import os
import socket
import threading
import time
import webbrowser

import uvicorn


def reserve_port(host: str, preferred_port: int, attempts: int = 100) -> socket.socket:
    """Reserve the first available port, so another process cannot take it first."""
    if not 0 <= preferred_port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    ports = [0] if preferred_port == 0 else range(preferred_port, min(preferred_port + attempts, 65536))
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.listen(socket.SOMAXCONN)
            return sock
        except OSError as exc:
            sock.close()
            if exc.errno != errno.EADDRINUSE:
                raise
    raise OSError(f"No free port found starting at {preferred_port}")


def _open_when_started(server: uvicorn.Server, url: str) -> None:
    for _ in range(200):
        if server.started:
            webbrowser.open(url)
            return
        if server.should_exit:
            return
        time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Trade Visualizer on a free local port")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    sock = reserve_port(args.host, args.port)
    port = sock.getsockname()[1]
    browser_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{browser_host}:{port}"
    print(f"Trade Visualizer: {url}", flush=True)
    config = uvicorn.Config("tradingview_mcp.ui.server:app", host=args.host, port=port)
    server = uvicorn.Server(config)
    if args.open_browser:
        threading.Thread(target=_open_when_started, args=(server, url), daemon=True).start()
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
