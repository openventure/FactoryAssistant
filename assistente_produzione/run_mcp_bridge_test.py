import argparse
import json
import os
import sys


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from assistente_produzione.modules.request_processing.mcp_bridge import (
        call_mcp_tool,
        discover_mcp_tools,
    )

    parser = argparse.ArgumentParser(
        description="Test locale del bridge MCP verso il server stdio."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Elenca i tool MCP disponibili e termina.",
    )
    parser.add_argument(
        "--tool",
        default="",
        help="Nome del tool MCP da invocare, per esempio find_articles_tool.",
    )
    parser.add_argument(
        "--args",
        default="{}",
        help='Argomenti del tool in formato JSON, per esempio {"format_filter":"60x120","limit":5}.',
    )

    args = parser.parse_args()
    tools = discover_mcp_tools(force_refresh=True)

    if args.list:
        print(json.dumps(tools, indent=2, ensure_ascii=False))
        return

    if not args.tool:
        parser.error("Specifica --tool oppure usa --list.")

    try:
        tool_args = json.loads(args.args or "{}")
    except json.JSONDecodeError as exc:
        parser.error(f"--args non ? un JSON valido: {exc}")

    if not isinstance(tool_args, dict):
        parser.error("--args deve rappresentare un oggetto JSON.")

    result = call_mcp_tool(args.tool, tool_args)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
