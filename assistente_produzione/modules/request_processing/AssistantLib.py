import openai
from openai import OpenAI
import os
from assistente_produzione.modules.request_processing.MaketheQuery import execute_sql_query, QueryRejectedError  # Import della funzione per eseguire query
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
from uuid import uuid4

# Definisci il fuso orario italiano
ITALIAN_TZ = pytz.timezone("Europe/Rome")
# Recupera la chiave API dalla variabile d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "knowledge" / "production_assistant_knowledge.md"
_CONVERSATIONS = {}
_TOKENIZER_FALLBACK_LOGGED_MODELS = set()
TOKENIZER_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "tokenizer_fallback.log"
CONVERSATION_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "conversations"


def _safe_json_dumps(obj):
    try:
        return json.dumps(obj, ensure_ascii=False, default=convert_decimal)
    except Exception:
        return str(obj)


def _get_response_usage(response):
    usage = getattr(response, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) if not isinstance(usage, dict) else usage.get("input_tokens")
    output_tokens = getattr(usage, "output_tokens", None) if not isinstance(usage, dict) else usage.get("output_tokens")
    total_tokens = getattr(usage, "total_tokens", None) if not isinstance(usage, dict) else usage.get("total_tokens")
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def log_conversation_event(conversation_id, event, request_id=None, payload=None):
    CONVERSATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CONVERSATION_LOG_DIR / f"{conversation_id}.log"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    payload_text = _safe_json_dumps(payload) if payload is not None else ""
    request_part = f" request_id={request_id}" if request_id else ""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] event={event}{request_part} payload={payload_text}\n")


def load_knowledge_instructions():
    if KNOWLEDGE_FILE.exists():
        return KNOWLEDGE_FILE.read_text(encoding="utf-8")
    return "Sei un assistente per analisi dati produzione. Rispondi in JSON."



def log_tokenizer_fallback(model_name, error):
    TOKENIZER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(TOKENIZER_LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"{timestamp} | fallback=cl100k_base | model={model_name} | error={error}\n"
        )

def get_token_encoding(model_name="gpt-4o"):
    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception as error:
        if model_name not in _TOKENIZER_FALLBACK_LOGGED_MODELS:
            log_tokenizer_fallback(model_name, str(error))
            _TOKENIZER_FALLBACK_LOGGED_MODELS.add(model_name)
        return tiktoken.get_encoding("cl100k_base")


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
    encoding = get_token_encoding(model)
    json_string = json.dumps(obj, default=convert_decimal, ensure_ascii=False)
    return len(encoding.encode(json_string)) 

def log_json_output(tool_output_dict, max_preview_chars=1000):
    try:
        # ✅ 1. Serializza il JSON in modo sicuro (conversione dei Decimal ecc.)
        json_string = json.dumps(tool_output_dict, indent=2, ensure_ascii=False, default=convert_decimal)

        # ✅ 2. Calcola i token del contenuto (modello GPT-4o)
        encoding = get_token_encoding(MODEL_NAME)
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

def extract_json_from_text(raw_text):
    """Estrae JSON valido anche da output markdown (```json ... ```) o testo misto."""
    if not isinstance(raw_text, str):
        raise ValueError("Il contenuto da parsare non è una stringa")

    candidate = raw_text.strip()
    if not candidate:
        raise ValueError("Contenuto vuoto")

    # 1) Caso ideale: il testo è già JSON puro
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 2) JSON dentro blocco markdown ```json ... ```
    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        fenced_content = fenced_match.group(1).strip()
        fenced_content = fix_trailing_comma(remove_json_comments(fenced_content))
        try:
            return json.loads(fenced_content)
        except json.JSONDecodeError:
            pass

    # 3) Estrazione best-effort del primo oggetto/array JSON dentro testo misto
    decoder = json.JSONDecoder()
    for token in ("{", "["):
        start = candidate.find(token)
        if start >= 0:
            try:
                parsed, _ = decoder.raw_decode(candidate[start:])
                return parsed
            except json.JSONDecodeError:
                continue

    raise ValueError("Nessun JSON valido trovato nell'output del modello")


def write_completejsonresult(json_string, file):
    try:
        print(f"✅ JSON start saving on '{file}'")

        # Estrae JSON robustamente anche da output markdown/testo misto
        json_data = extract_json_from_text(json_string)

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
           raise ValueError(f"Errore nella trascrizione del JSON: {str(e)}")
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
            "strict": False,
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
    request_id = f"req_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    req_start = time.perf_counter()
    try:
        instructions = load_knowledge_instructions()
        history = _CONVERSATIONS.setdefault(conversation_id, [])
        history.append({"role": "user", "content": user_input})
        estimated_input_tokens = count_tokens(history, model=MODEL_NAME)
        log_conversation_event(
            conversation_id,
            "request_started",
            request_id=request_id,
            payload={
                "user_input": user_input,
                "history_len": len(history),
                "estimated_input_tokens": estimated_input_tokens,
            },
        )

        tools_schema = build_tools_schema()
        api_start = time.perf_counter()
        response = client.responses.create(
            model=MODEL_NAME,
            instructions=instructions,
            input=history,
            tools=tools_schema,
            tool_choice="auto",
        )
        api_elapsed_ms = round((time.perf_counter() - api_start) * 1000, 2)
        log_conversation_event(
            conversation_id,
            "responses_create_completed",
            request_id=request_id,
            payload={"elapsed_ms": api_elapsed_ms, "usage": _get_response_usage(response)},
        )

        max_tool_rounds = 5
        rounds = 0
        while rounds < max_tool_rounds:
            rounds += 1
            tool_calls = get_tool_calls(response)
            log_conversation_event(
                conversation_id,
                "tool_calls_detected",
                request_id=request_id,
                payload={"round": rounds, "count": len(tool_calls)},
            )
            if not tool_calls:
                break

            tool_outputs = []
            for tool_call in tool_calls:
                if tool_call.name != "execute_sql_query":
                    continue

                arguments = json.loads(tool_call.arguments or "{}")
                query_sql = arguments.get("query_sql", "")

                query_error = None
                rejection_reason = None
                rejection_details = None
                query_estimated_tokens = count_tokens({"query_sql": query_sql}, model=MODEL_NAME)
                tool_start = time.perf_counter()
                try:
                    query_result = execute_sql_query(query_sql)
                except QueryRejectedError as exc:
                    query_result = None
                    query_error = str(exc)
                    rejection_reason = exc.reason
                    rejection_details = exc.details
                except Exception as exc:
                    query_result = None
                    query_error = str(exc)
                tool_elapsed_ms = round((time.perf_counter() - tool_start) * 1000, 2)
                log_conversation_event(
                    conversation_id,
                    "tool_execute_sql_query_completed",
                    request_id=request_id,
                    payload={
                        "round": rounds,
                        "elapsed_ms": tool_elapsed_ms,
                        "query_estimated_tokens": query_estimated_tokens,
                        "query_sql": query_sql,
                        "error": query_error,
                        "rejection_reason": rejection_reason,
                        "rejection_details": rejection_details,
                        "result_rows": len(query_result) if isinstance(query_result, list) else (1 if query_result else 0),
                    },
                )
                if rejection_reason:
                    log_conversation_event(
                        conversation_id,
                        "query_rejected",
                        request_id=request_id,
                        payload={
                            "round": rounds,
                            "reason": rejection_reason,
                            "details": rejection_details,
                        },
                    )

                if query_error:
                    output_payload = {
                        "message": "SQL_ERROR",
                        "error": query_error,
                        "failed_query": query_sql,
                        "hint": (
                            "Correggi la query e richiama execute_sql_query. "
                            "Usa una sola SELECT per tool-call; in SQL Server evita STRING_AGG(DISTINCT ...), "
                            "usa invece SELECT DISTINCT in subquery/CTE e poi STRING_AGG."
                        ),
                    }
                    output_json = json.dumps(output_payload, ensure_ascii=False)
                elif not query_result:
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

                output_estimated_tokens = count_tokens({"output": output_json}, model=MODEL_NAME)
                log_conversation_event(
                    conversation_id,
                    "tool_output_prepared",
                    request_id=request_id,
                    payload={
                        "round": rounds,
                        "call_id": tool_call.call_id,
                        "output_chars": len(output_json),
                        "output_estimated_tokens": output_estimated_tokens,
                    },
                )

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": output_json,
                    }
                )

            if not tool_outputs:
                break

            api_start = time.perf_counter()
            response = client.responses.create(
                model=MODEL_NAME,
                instructions=instructions,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=tools_schema,
                tool_choice="auto",
            )
            api_elapsed_ms = round((time.perf_counter() - api_start) * 1000, 2)
            log_conversation_event(
                conversation_id,
                "responses_create_after_tools_completed",
                request_id=request_id,
                payload={"round": rounds, "elapsed_ms": api_elapsed_ms, "usage": _get_response_usage(response)},
            )

        # Se abbiamo raggiunto il limite round e il modello continua a proporre tool-call,
        # forziamo una risposta finale senza ulteriori tool.
        pending_tool_calls = get_tool_calls(response)
        if rounds >= max_tool_rounds and pending_tool_calls:
            log_conversation_event(
                conversation_id,
                "max_tool_rounds_reached",
                request_id=request_id,
                payload={"rounds": rounds, "pending_tool_calls": len(pending_tool_calls)},
            )
            api_start = time.perf_counter()
            response = client.responses.create(
                model=MODEL_NAME,
                instructions=instructions,
                previous_response_id=response.id,
                input=[
                    {
                        "role": "system",
                        "content": "Interrompi ulteriori tool-call e fornisci ora la risposta finale in JSON schema usando solo i dati già disponibili.",
                    }
                ],
                tools=tools_schema,
                tool_choice="none",
            )
            api_elapsed_ms = round((time.perf_counter() - api_start) * 1000, 2)
            log_conversation_event(
                conversation_id,
                "responses_create_forced_finalization_completed",
                request_id=request_id,
                payload={"elapsed_ms": api_elapsed_ms, "usage": _get_response_usage(response)},
            )

        final_text = extract_response_text(response)
        if not final_text:
            # Fallback estremo: nuovo tentativo senza tool per evitare output vuoto.
            api_start = time.perf_counter()
            response = client.responses.create(
                model=MODEL_NAME,
                instructions=instructions,
                previous_response_id=response.id,
                input=[
                    {
                        "role": "system",
                        "content": "Fornisci ora una risposta finale valida in JSON schema. Non chiamare tool.",
                    }
                ],
                tools=tools_schema,
                tool_choice="none",
            )
            api_elapsed_ms = round((time.perf_counter() - api_start) * 1000, 2)
            log_conversation_event(
                conversation_id,
                "responses_create_empty_output_recovery_completed",
                request_id=request_id,
                payload={"elapsed_ms": api_elapsed_ms, "usage": _get_response_usage(response)},
            )
            final_text = extract_response_text(response)

        if not final_text:
            final_text = json.dumps({"message": "Nessuna risposta generata"}, ensure_ascii=False)

        total_elapsed_ms = round((time.perf_counter() - req_start) * 1000, 2)
        final_estimated_tokens = count_tokens({"final_text": final_text}, model=MODEL_NAME)
        log_conversation_event(
            conversation_id,
            "request_completed",
            request_id=request_id,
            payload={
                "elapsed_ms": total_elapsed_ms,
                "final_text_chars": len(final_text),
                "final_estimated_tokens": final_estimated_tokens,
                "usage": _get_response_usage(response),
            },
        )

        history.append({"role": "assistant", "content": final_text})
        try:
            write_completejsonresult(final_text, "data.json")
        except ValueError:
            write_message_to_json(final_text)
        return final_text
    except Exception as e:
        total_elapsed_ms = round((time.perf_counter() - req_start) * 1000, 2)
        log_conversation_event(
            conversation_id,
            "request_failed",
            request_id=request_id,
            payload={"elapsed_ms": total_elapsed_ms, "error": str(e)},
        )
        error_msg = f"Errore: {str(e)}"
        write_message_to_json(error_msg)
        return error_msg
