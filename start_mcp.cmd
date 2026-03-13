cd \projects\openventure\FactoryAssistance
call env\Scripts\activate
set PYTHONPATH=%CD%
SET DEBUG_MODE=False
Set PYDEVD_DISABLE_FILE_VALIDATION=1
SET MCP_DEBUGPY=1

python assistente_produzione/run_mcp_server.py
pause
