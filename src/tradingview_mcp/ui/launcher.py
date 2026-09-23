"""Launch the dashboard alongside other local copies of the project."""

import argparse
import os
import threading
import time
import webbrowser

import uvicorn

from tradingview_mcp.core.utils.ports import reserve_port


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
    parser.add_argument("--strict-port", action="store_true",
                        help="Fail if --port is busy instead of moving to the next free port "
                             "(also: PORT_STRICT=1)")
    args = parser.parse_args()

    strict = args.strict_port or os.environ.get("PORT_STRICT", "0") == "1"
    attempts = 1 if strict else int(os.environ.get("PORT_MAX_TRIES", "100"))
    sock = reserve_port(args.host, args.port, attempts)
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
