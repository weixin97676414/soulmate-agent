















from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys

HANDSHAKE_PREFIX = "AGENT_CORE_READY"
DEV_DEFAULT_PORT = 8756  


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="my_agent", description="Agent Core 服务进程")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，出于安全默认仅本机")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("AGENT_PORT", "0")),
        help="监听端口，0 表示由系统分配空闲端口",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("AGENT_DATA_DIR", ""),
        help="用户数据根目录，默认 %%APPDATA%%/AgentDesktop",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AGENT_TOKEN", ""),
        help="本地访问令牌，留空则自动生成并打印",
    )
    parser.add_argument("--log-level", default=os.environ.get("AGENT_LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--reload",
        action="store_true",
        help=f"开发模式：热重载（会将端口固定为 {DEV_DEFAULT_PORT}）",
    )
    return parser.parse_args(argv)


def _bind_socket(host: str, port: int) -> tuple[socket.socket, int]:

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        print(
            f"无法绑定 {host}:{port} —— {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    sock.listen(128)
    sock.set_inheritable(True)
    return sock, sock.getsockname()[1]


def _emit_handshake(port: int, token: str) -> None:
    payload = {"port": port, "token": token, "pid": os.getpid()}
    
    print(f"{HANDSHAKE_PREFIX} {json.dumps(payload)}", flush=True)


def _build_runtime(data_dir: str, log_level: str):
    import logging

    from .config.paths import AppPaths
    from .errors import AgentError
    from .observability.logger import setup_logging
    from .server.runtime import AppRuntime

    paths = AppPaths.resolve(data_dir or None).ensure()
    setup_logging(level=log_level, logs_dir=paths.logs_dir)
    try:
        return AppRuntime(paths)
    except AgentError as exc:
        logging.getLogger(__name__).error("启动失败: %s", exc.message)
        raise SystemExit(3) from exc


def create_app_for_reload():

    from .config.paths import AppPaths
    from .observability.logger import setup_logging
    from .server.app import create_app
    from .server.runtime import AppRuntime

    paths = AppPaths.resolve(os.environ.get("AGENT_DATA_DIR") or None).ensure()
    setup_logging(
        level=os.environ.get("AGENT_LOG_LEVEL", "INFO"),
        logs_dir=paths.logs_dir,
    )
    runtime = AppRuntime(paths)
    return create_app(runtime=runtime, token=os.environ.get("AGENT_TOKEN", ""))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    
    
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  
                pass

    
    
    if argv and argv[0] == "mcp-sample":
        from .mcp.sample_server import main as sample_main

        return sample_main(argv[1:])
    
    
    if argv and argv[0] == "mcp-sqlite":
        from .mcp.sqlite_server import main as sqlite_main

        return sqlite_main(argv[1:])

    
    
    
    if argv and argv[0] == "self-check":
        from .diagnostics import main as self_check_main

        return self_check_main(argv[1:])

    
    
    
    if argv and argv[0] in ("skills", "run", "replay"):
        from .server.cli import main as cli_main

        return cli_main(argv)

    args = parse_args(argv)

    import uvicorn

    token = args.token or secrets.token_urlsafe(24)
    os.environ["AGENT_TOKEN"] = token
    if args.data_dir:
        os.environ["AGENT_DATA_DIR"] = args.data_dir

    if args.reload:
        
        _emit_handshake(DEV_DEFAULT_PORT, token)
        uvicorn.run(
            "my_agent.__main__:create_app_for_reload",
            factory=True,
            host=args.host,
            port=DEV_DEFAULT_PORT,
            reload=True,
            reload_dirs=[str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))],
            log_level=args.log_level.lower(),
            access_log=False,
        )
        return 0

    runtime = _build_runtime(args.data_dir, args.log_level)
    from .server.app import create_app

    app = create_app(runtime=runtime, token=token)
    sock, port = _bind_socket(args.host, args.port)

    config = uvicorn.Config(
        app,
        log_level=args.log_level.lower(),
        access_log=False,
        
        timeout_keep_alive=75,
    )
    server = uvicorn.Server(config)
    app.state.uvicorn_server = server

    _emit_handshake(port, token)
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:  
        pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
