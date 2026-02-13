import openai
from openai import OpenAI
import os
from assistente_produzione.modules.request_processing.MaketheQuery import execute_sql_query  # Import della funzione per eseguire query
from assistente_produzione.modules.visualization.test_ui import datamanger_assistant  # Import della funzione per eseguire query
import time
import json
import decimal
import datetime
import pytz
import re
import shutil
import tiktoken
from pathlib import Path

# Definisci il fuso orario italiano
ITALIAN_TZ = pytz.timezone("Europe/Rome")
# Recupera la chiave API dalla variabile d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "knowledge" / "production_assistant_knowledge.md"
_CONVERSATIONS = {}


def load_knowledge_instructions():
    if KNOWLEDGE_FILE.exists():
        return KNOWLEDGE_FILE.read_text(encoding="utf-8")
    return "Sei un assistente per analisi dati produzione. Rispondi in JSON."

# Funzione per calcolare i token di un oggetto Python serializzato in JSON
def replace_table_data_in_message(last_message, query_result):
    import re

    # Estrai il testo vero e proprio
    text_block = last_message[0].text.value.strip()

    # Estrai JSON se racchiuso in ```json ... ```
    if text_block.startswith("```json"):
        json_match = re.search(r'```json\n(.*?)\n```', text_block, re.DOTALL)
        if json_match:
            json_string = json_match.group(1)
        else:
            raise ValueError("⚠️ JSON non trovato nel blocco markdown.")
    else:
        json_string = text_block

    # Pulisce il JSON se necessario (definizioni custom)
    clean_json = fix_trailing_comma(remove_json_comments(json_string))

    # Converte in oggetto Python
    data = json.loads(clean_json)

    # Sostituisce la proprietà "table_data"
    data["table_data"] = query_result

    # Ricrea la stringa JSON aggiornata
    new_json_output = json.dumps(data, indent=4, ensure_ascii=False, default=convert_decimal)
    return new_json_output

def count_tokens(obj, model="gpt-4o"):
    encoding = tiktoken.encoding_for_model(model)
    json_string = json.dumps(obj, default=convert_decimal, ensure_ascii=False)
    return len(encoding.encode(json_string)) 

def log_json_output(tool_output_dict, max_preview_chars=1000):
    try:
        # ✅ 1. Serializza il JSON in modo sicuro (conversione dei Decimal ecc.)
        json_string = json.dumps(tool_output_dict, indent=2, ensure_ascii=False, default=convert_decimal)

        # ✅ 2. Calcola i token del contenuto (modello GPT-4o)
        encoding = tiktoken.encoding_for_model("gpt-4o")
        token_count = len(encoding.encode(json_string))

        print("✅ JSON valido da inviare all'assistente")
        print(f"🔢 Token stimati: {token_count}")
        print(f"📦 Dimensione stringa JSON: {len(json_string)} caratteri")

        # ✅ 3. Stampa anteprima (opzionale)
        preview = json_string[:max_preview_chars]
        print(f"🔍 Preview del JSON (max {max_preview_chars} caratteri):\n{preview}")
        if len(json_string) > max_preview_chars:
            print("🔽 ... (contenuto troncato per anteprima)")

        # ✅ 4. Salva anche su file (opzionale per debug)
        with open("tool_output_debug.json", "a", encoding="utf-8") as f:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            f.write(timestamp + ": " +json_string + "\n")

        return json_string  # Utile se vuoi riutilizzare

    except Exception as e:
        print("❌ Errore nella serializzazione del JSON da inviare all'assistente:")
        print(str(e))
        raise e
# Funzione per convertire Decimal in JSON-safe (float o string)
def convert_decimal(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)  # Converti i numeri Decimal in float
    elif isinstance(obj, datetime.datetime):
        # Converte il datetime in stringa con fuso orario italiano
        return obj.astimezone(ITALIAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(obj, datetime.date):
        # Se è solo una data, formattala senza ora
        return obj.strftime("%Y-%m-%d")
    raise TypeError(f"Type {type(obj)} not serializable")

# Funzione per scrivere messaggi nel file JSON
def write_message_to_json(message):
    file_path = "data.json"
        
    # Creiamo un nuovo dizionario con solo "message"
    data = {"message": message}
    
    # Scriviamo il nuovo contenuto nel file, sovrascrivendo tutto
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Funzione per scrivere il testo nel file JSON
def write_text_to_json(text):
    file_path = "data.json"
        
    # Creiamo un nuovo dizionario con solo "message"
    data = {"text": text}
    
    # Scriviamo il nuovo contenuto nel file, sovrascrivendo tutto
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def remove_json_comments(json_string):
    """Rimuove i commenti JSON (// e /* */) da una stringa JSON."""
    json_string = re.sub(r"//.*", "", json_string)  # Rimuove commenti singola riga
    json_string = re.sub(r"/\*.*?\*/", "", json_string, flags=re.DOTALL)  # Rimuove commenti multi-linea
    return json_string.strip()
def fix_trailing_comma(json_string):
    """
    Rimuove la virgola finale nell'ultimo elemento di un array JSON.
    """
    # Rimuove la virgola finale prima di una chiusura di array `]` o di oggetto `}`
    json_string = re.sub(r",\s*([\]}])", r"\1", json_string)
    return json_string.strip()

def write_completejsonresult(json_string, file):
    try:
        print(f"✅ JSON start saving on '{file}'")
        
        # Pulizia della stringa JSON
        clean_json_string = remove_json_comments(json_string)
        fixed_json = fix_trailing_comma(clean_json_string)
        try:
            # 🔹 2. Converte la stringa JSON in un oggetto Python
            json_data = json.loads(fixed_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Errore nella conversione del JSON: {e}")

        # 🔹 3. Salva il JSON in un file
        file_path = file
        with open(file_path, "w", encoding="utf-8") as json_file:
            json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        print(f"✅ JSON salvato con successo in '{file_path}'")

        # Crea un timestamp formattato come YYYYMMDD_HHMMSS
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Crea il nuovo percorso del file concatenando il timestamp a file_path
        new_file_path = f"{file_path}_{timestamp}"

        # Copia il file file_path in new_file_path
        shutil.copy(file_path, new_file_path)
        print(f"Il file è stato copiato in: {new_file_path}")
        
    except Exception as e:
           return f"Errore nella trascrizione del JSON: {str(e)}"
def extract_response_text(response):
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    chunks = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for content in getattr(item, "content", []) or []:
                text_value = getattr(content, "text", None)
                if isinstance(text_value, str):
                    chunks.append(text_value)
                elif hasattr(text_value, "value"):
                    chunks.append(text_value.value)
    return "\n".join(chunks).strip()


def get_tool_calls(response):
    calls = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "function_call":
            calls.append(item)
    return calls


def build_tools_schema():
    return [
        {
            "type": "function",
            "name": "execute_sql_query",
            "description": "Esegue una query SQL e restituisce i risultati.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_sql": {
                        "type": "string",
                        "description": "Query SQL da eseguire",
                    }
                },
                "required": ["query_sql"],
            },
        }
    ]


def handle_request(user_input, thread_id=None):
    """Gestisce una richiesta utente usando Responses API + tool calling."""
    conversation_id = thread_id or "default"
    try:
        instructions = load_knowledge_instructions()
        history = _CONVERSATIONS.setdefault(conversation_id, [])
        history.append({"role": "user", "content": user_input})

        response = client.responses.create(
            model=MODEL_NAME,
            instructions=instructions,
            input=history,
            tools=build_tools_schema(),
            tool_choice="auto",
        )

        max_tool_rounds = 5
        rounds = 0
        while rounds < max_tool_rounds:
            rounds += 1
            tool_calls = get_tool_calls(response)
            if not tool_calls:
                break

            tool_outputs = []
            for tool_call in tool_calls:
                if tool_call.name != "execute_sql_query":
                    continue

                arguments = json.loads(tool_call.arguments or "{}")
                query_sql = arguments.get("query_sql", "")
                query_result = execute_sql_query(query_sql)

                if not query_result:
                    output_payload = {
                        "message": "⚠️ Nessun dato disponibile per la query richiesta."
                    }
                    output_json = json.dumps(output_payload, ensure_ascii=False)
                else:
                    max_tokens = 10000
                    truncated_result = query_result[:]
                    while count_tokens(truncated_result) > max_tokens and len(truncated_result) > 1:
                        truncated_result = truncated_result[:-1]

                    is_partial = len(truncated_result) < len(query_result)
                    partial_message = (
                        "⚠️ Nota: I risultati mostrati sono parziali. Per una lista completa, restringi la ricerca."
                        if is_partial
                        else "⚠️ Nota: I risultati mostrati sono completi"
                    )

                    tool_payload = {
                        "user_request": user_input,
                        "report_title": "Analisi dei dati richiesti",
                        "summary": "Ecco una sintesi dei dati recuperati dalla query eseguita.",
                        "table_data": truncated_result,
                        "conclusions": "Analizza questi dati e fornisci una valutazione dei trend e delle informazioni più rilevanti.",
                        "note": partial_message,
                        "format": "JSON",
                    }
                    output_json = log_json_output(tool_payload)

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": output_json,
                    }
                )

            if not tool_outputs:
                break

            response = client.responses.create(
                model=MODEL_NAME,
                instructions=instructions,
                previous_response_id=response.id,
                input=tool_outputs,
            )

        final_text = extract_response_text(response)
        if not final_text:
            final_text = json.dumps({"message": "Nessuna risposta generata"}, ensure_ascii=False)

        history.append({"role": "assistant", "content": final_text})
        write_completejsonresult(final_text, "data.json")
        return final_text
    except Exception as e:
        error_msg = f"Errore: {str(e)}"
        write_message_to_json(error_msg)
        return error_msg
