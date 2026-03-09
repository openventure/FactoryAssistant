import openai
import os
import re
from sqlalchemy import create_engine, text
import datetime

# Recupera la chiave API
#OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
#openai.api_key = OPENAI_API_KEY

# ID dell'assistente esistente
#ASSISTANT_ID = "tuo_assistant_id"

# Configurazione dei database
#SQLSERVER_URL = "mssql+pyodbc://dbadmin:dbadmin@(local)/EasyPlanner?driver=ODBC+Driver+17+for+SQL+Server"
SQL_HOSTNAME = "(local)"
# Configurazione dei database
SQLSERVER_CONNECTION_STRING = (
    "Driver={SQL Server};"
    f"Server={SQL_HOSTNAME};"
    "Database=EasyPlanner;"
    "Trusted_Connection=no;"
    "UID=dbadmin;"
    "PWD=dbadmin;"
)
#SQLSERVER_URL2 = "mssql+pyodbc://dbadmin:dbadmin@(local)/Produzione?driver=ODBC+Driver+17+for+SQL+Server"
# Configurazione dei database
SQLSERVER_CONNECTION_STRING2 = (
    "Driver={SQL Server};"
    f"Server={SQL_HOSTNAME};"
    "Database=Produzione;"
    "Trusted_Connection=no;"
    "UID=dbadmin;"
    "PWD=dbadmin;"
)
sqlite_path = os.getenv("SQLITE_PATH")  #r"C:\projects\GruppoFrascariCeramiche\ACR\prj\triunfo\db_produzione.sqlite3" #os.getenv("SQLITE_PATH")
SQLITE_URL = f"sqlite:///{sqlite_path}"

#engine_sqlserver = create_engine(SQLSERVER_URL)
#engine_sqlserver2 = create_engine(SQLSERVER_URL)

connection_string = f"mssql+pyodbc:///?odbc_connect={SQLSERVER_CONNECTION_STRING}"
engine_sqlserver = create_engine(connection_string)

connection_string2 = f"mssql+pyodbc:///?odbc_connect={SQLSERVER_CONNECTION_STRING2}"
engine_sqlserver2 = create_engine(connection_string2)

engine_sqlite = create_engine(SQLITE_URL)

MAX_QUERY_ROWS = 10000


class QueryRejectedError(Exception):
    """Errore esplicito per query rigettate da regole applicative."""

    def __init__(self, reason: str, details=None):
        self.reason = reason
        self.details = details or {}
        super().__init__(f"QUERY_REJECTED reason={reason} details={self.details}")

def extract_table_name(query_sql: str):
    """Estrae il nome tabella dal primo FROM, supportando schema (es. dbo.PALLET_PRODUCTION)."""
    match = re.search(r'FROM\s+((?:\[[^\]]+\]|[\w]+)(?:\.(?:\[[^\]]+\]|[\w]+))?)', query_sql, re.IGNORECASE)
    if not match:
        return None

    full_name = match.group(1).strip()
    parts = [p.strip('[] ') for p in full_name.split('.') if p.strip()]
    return parts[-1] if parts else None


def split_sql_statements(query_sql: str):
    """Divide gli statement SQL su ';' ignorando i ';' dentro stringhe SQL."""
    statements = []
    current = []
    in_single_quote = False
    i = 0
    while i < len(query_sql):
        ch = query_sql[i]

        if ch == "'":
            # Gestione escape SQL: '' dentro stringa
            if in_single_quote and i + 1 < len(query_sql) and query_sql[i + 1] == "'":
                current.append("''")
                i += 2
                continue
            in_single_quote = not in_single_quote
            current.append(ch)
            i += 1
            continue

        if ch == ';' and not in_single_quote:
            statement = ''.join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = ''.join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def qualify_unqualified_table(query_sql: str, table_name: str, schema: str = "dbo"):
    """Qualifica solo riferimenti non già qualificati (evita `dbo.dbo.tabella`)."""
    pattern = rf"(?<![.\]])\b{re.escape(table_name)}\b"
    return re.sub(pattern, f"{schema}.{table_name}", query_sql)


def execute_sql_query(query_sql: str):
    statements = split_sql_statements(query_sql)
    if len(statements) != 1:
        raise QueryRejectedError(
            reason="multiple_statements_detected",
            details={
                "statement_count": len(statements),
                "statement_previews": [s[:120] for s in statements[:3]],
                "hint": "Usa una sola SELECT per tool-call (CTE/subquery) oppure effettua più tool-call separate.",
            },
        )

    query_sql = statements[0]

    with open("query.log", "a", encoding="utf-8") as log_file:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file.write(timestamp + ": " + query_sql + "\n")
    """Esegue la query SQL ricevuta dall'assistente e restituisce i risultati."""
    table_name = extract_table_name(query_sql)
    if not table_name:
        raise ValueError("Impossibile determinare la tabella dalla query SQL.")
    
    # Determina quale database usare
    if table_name in ["app_laboratorydata", "app_assorbimento"]:
        engine = engine_sqlite        
    elif table_name in ["PALLET_PRODUCTION"]:
        engine = engine_sqlserver2
        query_sql = qualify_unqualified_table(query_sql, table_name, schema="dbo")
    else:
        engine = engine_sqlserver
    
    with engine.connect() as connection:
        result = connection.execute(text(query_sql))
        rows = result.fetchmany(MAX_QUERY_ROWS + 1)

        if not rows:  # Se la query non ha restituito dati
            return None

        was_truncated = len(rows) > MAX_QUERY_ROWS
        if was_truncated:
            rows = rows[:MAX_QUERY_ROWS]

        # Se il risultato e un solo valore numerico (es. COUNT(*))
        if len(rows) == 1 and len(rows[0]) == 1:
            return rows[0][0]

        # Se il risultato e una tabella con piu colonne
        mapped_rows = [dict(row._mapping) for row in rows]
        if was_truncated:
            print(f"Query troncata a {MAX_QUERY_ROWS} righe per contenere tempi e payload.")
        return mapped_rows

# Creazione dell'assistente con nuove istruzioni
"""response = openai.beta.assistants.create(
    name="Analisi Dati Produzione",
    instructions=instructions,
    model="gpt-4-turbo",
    tools=tools
)"""

# Recupera l'assistente esistente
"""assistant = openai.beta.assistants.retrieve(ASSISTANT_ID)
print("Assistant ID:", assistant.id)
"""
# Test della funzione se eseguito direttamente
if __name__ == "__main__":
    test_query = """
    SELECT COUNT(*) AS NumPalletProdottiCorrente 
    FROM PALLET_PRODUCTION
    WHERE MONTH(START_DATETIME) = MONTH(GETDATE())
    AND YEAR(START_DATETIME) = YEAR(GETDATE());
    """
    try:
        result = execute_sql_query(test_query)
        print("Risultato della query di test:", result)
    except Exception as e:
        print("Errore durante l'esecuzione della query:", str(e))