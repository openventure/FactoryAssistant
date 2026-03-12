# Factory Assistance MCP Server

Primo skeleton MCP locale per il progetto Factory Assistance.

## Stato attuale
- Trasporto previsto: `stdio`
- Linguaggio: Python
- Tool disponibili:
  - `find_articles_tool`
  - `get_understock_articles_tool`
- Fonte dati corrente: tabella `pa_ff_code`

## Avvio locale
Dopo avere installato la dipendenza `mcp`:

```bash
python assistente_produzione/run_mcp_server.py
```

## Note architetturali
- Il server e locale: non richiede un servizio HTTP separato.
- La chat potra poi collegarsi al server MCP come processo figlio via `stdio`.
- La service layer e in `assistente_produzione/mcp_server/stock_service.py` e riusa i motori SQLAlchemy gia presenti nel progetto.
