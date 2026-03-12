import os
import sys


def _maybe_enable_debugpy() -> None:
    if os.getenv("MCP_DEBUGPY", "0").lower() not in {"1", "true", "yes", "on"}:
        return

    import debugpy

    host = os.getenv("MCP_DEBUGPY_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_DEBUGPY_PORT", "5678"))
    wait_for_client = os.getenv("MCP_DEBUGPY_WAIT", "0").lower() in {"1", "true", "yes", "on"}

    debugpy.listen((host, port))
    print(f"[MCP] debugpy in ascolto su {host}:{port}", file=sys.stderr, flush=True)
    if wait_for_client:
        print("[MCP] attendo il debugger...", file=sys.stderr, flush=True)
        debugpy.wait_for_client()


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    _maybe_enable_debugpy()

    from assistente_produzione.mcp_server.server import main as run_server

    run_server()


if __name__ == "__main__":
    main()
