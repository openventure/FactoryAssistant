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
# Configurazione dei database
SQLSERVER_CONNECTION_STRING = (
    "Driver={SQL Server};"
    "Server=(local);"
    "Database=EasyPlanner;"
    "Trusted_Connection=no;"
    "UID=dbadmin;"
    "PWD=dbadmin;"
)
#SQLSERVER_URL2 = "mssql+pyodbc://dbadmin:dbadmin@(local)/Produzione?driver=ODBC+Driver+17+for+SQL+Server"
# Configurazione dei database
SQLSERVER_CONNECTION_STRING2 = (
    "Driver={SQL Server};"
    "Server=(local);"
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

def extract_table_name(query_sql: str):
    """Estrae il nome della tabella dalla query SQL."""
    match = re.search(r'FROM\s+([\w\d_]+)', query_sql, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def execute_sql_query(query_sql: str):
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
        query_sql = query_sql.replace(table_name, f"dbo.{table_name}")
    else:
        engine = engine_sqlserver
    
    with engine.connect() as connection:
        result = connection.execute(text(query_sql))
        rows = result.fetchall()

        if not rows:  # 🔹 Se la query non ha restituito dati
            return None  

        # 🔹 Se il risultato è un solo valore numerico (es. COUNT(*))
        if len(rows) == 1 and isinstance(rows[0], tuple) and len(rows[0]) == 1:
            return rows[0][0]  # 🔥 Ritorna l'intero direttamente

        # 🔹 Se il risultato è una tabella con più colonne
        return [dict(row._mapping) for row in rows]  # Converte il risultato in dizionario

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