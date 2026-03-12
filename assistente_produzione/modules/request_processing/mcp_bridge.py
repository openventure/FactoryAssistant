import json
import os
import sys
import time
import datetime
from pathlib import Path
from typing import Any

import anyio

try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # pragma: no cover - dipendenza opzionale
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None
    _MCP_IMPORT_ERROR = exc
else:
    _MCP_IMPORT_ERROR = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = Path(__file__).resolve().parents[2]
MCP_RUNNER = APP_ROOT / "run_mcp_server.py"
MCP_STDERR_LOG = APP_ROOT / "logs" / "mcp_client_stderr.log"
_MCP_TOOLS_CACHE: dict[str, Any] = {"expires_at": 0.0, "tools": []}
_CACHE_TTL_SECONDS = 15.0


class MCPBridgeError(RuntimeError):
    """Errore di integrazione con il server MCP locale."""


def _append_mcp_client_log(event: str, payload: dict[str, Any] | None = None) -> None:
    MCP_STDERR_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    payload_text = json.dumps(payload or {}, ensure_ascii=False, default=str)
    with open(MCP_STDERR_LOG, "a", encoding="utf-8") as errlog:
        errlog.write(f"[{timestamp}] client_event={event} payload={payload_text}\n")


def is_mcp_available() -> bool:
    return ClientSession is not None and MCP_RUNNER.exists()


def _server_parameters():
    if not is_mcp_available():
        message = "MCP non disponibile: libreria non installata oppure run_mcp_server.py assente."
        if _MCP_IMPORT_ERROR is not None:
            raise MCPBridgeError(message) from _MCP_IMPORT_ERROR
        raise MCPBridgeError(message)

    env = {
        "PYTHONUNBUFFERED": "1",
    }
    if os.getenv("MCP_DEBUGPY"):
        env["MCP_DEBUGPY"] = os.getenv("MCP_DEBUGPY", "")
        env["MCP_DEBUGPY_PORT"] = os.getenv("MCP_DEBUGPY_PORT", "5678")
        env["MCP_DEBUGPY_HOST"] = os.getenv("MCP_DEBUGPY_HOST", "127.0.0.1")
        env["MCP_DEBUGPY_WAIT"] = os.getenv("MCP_DEBUGPY_WAIT", "0")

    return StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_RUNNER)],
        cwd=str(PROJECT_ROOT),
        env=env,
    )


async def _run_with_session(callback):
    MCP_STDERR_LOG.parent.mkdir(parents=True, exist_ok=True)
    params = _server_parameters()
    with open(MCP_STDERR_LOG, "a", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await callback(session)


async def _discover_mcp_tools_async():
    async def _callback(session):
        result = await session.list_tools()
        tools = []
        for tool in result.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or getattr(tool.annotations, "title", None) or tool.name,
                    "parameters": _normalize_schema(tool.inputSchema),
                }
            )
        return tools

    return await _run_with_session(_callback)


async def _call_mcp_tool_async(tool_name: str, arguments: dict[str, Any] | None = None):
    async def _callback(session):
        return await session.call_tool(tool_name, arguments=arguments or {})

    result = await _run_with_session(_callback)
    return _normalize_call_result(result)


def _normalize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    return normalized


def _normalize_call_result(result) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        payload = dict(structured)
        payload.setdefault("is_error", bool(getattr(result, "isError", False)))
        return payload

    content_blocks = []
    text_chunks = []
    for block in getattr(result, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_chunks.append(getattr(block, "text", ""))
        if hasattr(block, "model_dump"):
            content_blocks.append(block.model_dump(mode="json", exclude_none=True))
        else:
            content_blocks.append(str(block))

    payload = {
        "is_error": bool(getattr(result, "isError", False)),
        "content": content_blocks,
    }
    if text_chunks:
        payload["text"] = "\n".join(chunk for chunk in text_chunks if chunk)
    return payload


def discover_mcp_tools(force_refresh: bool = False) -> list[dict[str, Any]]:
    if not is_mcp_available():
        return []

    _append_mcp_client_log("discover_tools_requested", {"force_refresh": force_refresh})

    now = time.monotonic()
    if not force_refresh and _MCP_TOOLS_CACHE["tools"] and _MCP_TOOLS_CACHE["expires_at"] > now:
        return list(_MCP_TOOLS_CACHE["tools"])

    tools = anyio.run(_discover_mcp_tools_async)
    _append_mcp_client_log("discover_tools_completed", {"count": len(tools), "tool_names": [tool.get("name") for tool in tools]})
    _MCP_TOOLS_CACHE["tools"] = list(tools)
    _MCP_TOOLS_CACHE["expires_at"] = now + _CACHE_TTL_SECONDS
    return list(tools)


def get_openai_tool_schemas() -> list[dict[str, Any]]:
    schemas = []
    for tool in discover_mcp_tools():
        schemas.append(
            {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "strict": False,
                "parameters": tool["parameters"],
            }
        )
    return schemas


def get_mcp_tool_names() -> set[str]:
    return {tool["name"] for tool in discover_mcp_tools()}


def call_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if tool_name not in get_mcp_tool_names():
        raise MCPBridgeError(f"Tool MCP non disponibile: {tool_name}")

    payload = {"tool_name": tool_name, "arguments": arguments or {}}
    _append_mcp_client_log("tool_call_requested", payload)
    result = anyio.run(_call_mcp_tool_async, tool_name, arguments or {})
    _append_mcp_client_log(
        "tool_call_completed",
        {
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result_keys": sorted(result.keys()) if isinstance(result, dict) else None,
            "is_error": bool(result.get("is_error")) if isinstance(result, dict) else None,
        },
    )
    return result
