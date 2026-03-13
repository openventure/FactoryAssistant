import openai
from openai import OpenAI
import os
from assistente_produzione.modules.request_processing.MaketheQuery import execute_sql_query, QueryRejectedError  # Import della funzione per eseguire query
from assistente_produzione.modules.request_processing.mcp_bridge import MCPBridgeError, call_mcp_tool, get_mcp_tool_names, get_openai_tool_schemas
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
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5-mini")
KNOWLEDGE_FILE = Path(__file__).resolve().parents[2] / "knowledge" / "production_assistant_knowledge.md"
_CONVERSATIONS = {}
_TOKENIZER_FALLBACK_LOGGED_MODELS = set()
TOKENIZER_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "tokenizer_fallback.log"
CONVERSATION_LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "conversations"


class SemanticValidationError(RuntimeError):
    """Risposta finale del modello strutturalmente valida ma semanticamente incoerente."""


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


def _coerce_scalar_for_table(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, datetime.datetime):
        return value.astimezone(ITALIAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, datetime.date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _normalize_table_data_rows(table_data):
    if not isinstance(table_data, list):
        return []

    normalized = []
    for item in table_data:
        if isinstance(item, dict) and isinstance(item.get("rows"), list):
            dataset_name = item.get("dataset")
            for row in item["rows"]:
                if isinstance(row, dict):
                    flat_row = {key: _coerce_scalar_for_table(value) for key, value in row.items() if not isinstance(value, (list, dict))}
                    if dataset_name and "dataset" not in flat_row:
                        flat_row["dataset"] = dataset_name
                    normalized.append(flat_row)
            continue

        if isinstance(item, dict):
            normalized.append({key: _coerce_scalar_for_table(value) for key, value in item.items() if not isinstance(value, (list, dict))})

    return normalized


def _contains_total_like_text(value):
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in {"total", "totale", "riepilogo", "subtotal", "subtotale"} or normalized.startswith("total ") or normalized.startswith("totale ")


def _semantic_validation_reason(message):
    lowered = str(message).lower()
    if "chiavi diverse" in lowered:
        return "table_data_inconsistent_keys"
    if "totale/riepilogo" in lowered:
        return "table_data_total_row"
    if "valori nulli" in lowered:
        return "narrative_claims_missing_nulls"
    if "totale reale non verificato" in lowered:
        return "narrative_unverified_total_count"
    if "non e un oggetto json" in lowered:
        return "final_response_not_json_object"
    if "chiavi obbligatorie mancanti" in lowered:
        return "missing_required_top_level_keys"
    if "table_data deve essere una lista" in lowered:
        return "table_data_not_list"
    if "non e un oggetto-riga" in lowered:
        return "table_data_non_object_row"
    return "semantic_validation_failed"


def _validate_final_response_semantics(final_text):
    data = extract_json_from_text(final_text)
    if not isinstance(data, dict):
        raise SemanticValidationError("La risposta finale non e un oggetto JSON.")

    required_keys = {"user_request", "report_title", "summary", "table_data", "conclusions"}
    missing = required_keys.difference(data.keys())
    if missing:
        raise SemanticValidationError(f"Chiavi obbligatorie mancanti: {sorted(missing)}")

    table_data = data.get("table_data")
    if not isinstance(table_data, list):
        raise SemanticValidationError("table_data deve essere una lista.")

    expected_keys = None
    for index, row in enumerate(table_data):
        if not isinstance(row, dict):
            raise SemanticValidationError(f"table_data[{index}] non e un oggetto-riga.")

        row_keys = set(row.keys())
        if expected_keys is None:
            expected_keys = row_keys
        elif row_keys != expected_keys:
            raise SemanticValidationError(
                f"table_data contiene righe con chiavi diverse: attese {sorted(expected_keys)}, trovate {sorted(row_keys)} alla riga {index}."
            )

        for value in row.values():
            if _contains_total_like_text(value):
                raise SemanticValidationError("table_data contiene una riga di totale/riepilogo non ammessa.")

    summary = str(data.get("summary", ""))
    conclusions = str(data.get("conclusions", ""))
    narrative_text = f"{summary}\n{conclusions}".lower()

    if ("valore nullo" in narrative_text or "valori nulli" in narrative_text) and not any(
        value is None
        for row in table_data
        for value in row.values()
    ):
        raise SemanticValidationError("La narrativa cita valori nulli non presenti nei dati restituiti.")

    row_count = len(table_data)
    found_patterns = [
        f"sono stati trovati {row_count}",
        f"sono stati individuati {row_count}",
        f"sono presenti {row_count}",
    ]
    if row_count >= 50 and any(pattern in narrative_text for pattern in found_patterns):
        raise SemanticValidationError("La narrativa presenta il numero di righe restituite come totale reale non verificato.")

    return data


def _normalize_final_response_json(final_text):
    try:
        data = extract_json_from_text(final_text)
    except Exception:
        return final_text

    if not isinstance(data, dict):
        return final_text

    expected_keys = {"user_request", "report_title", "summary", "table_data", "conclusions"}
    if not expected_keys.issubset(data.keys()):
        return final_text

    data = {
        "user_request": str(data.get("user_request", "")),
        "report_title": str(data.get("report_title", "")),
        "summary": str(data.get("summary", "")),
        "table_data": _normalize_table_data_rows(data.get("table_data", [])),
        "conclusions": str(data.get("conclusions", "")),
    }
    return json.dumps(data, ensure_ascii=False, indent=4)


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


def _build_function_call_output(call_id, output_json):
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output_json,
    }


def _truncate_items_payload(payload, max_tokens=10000):
    if not isinstance(payload, dict):
        return payload

    items = payload.get("items")
    if not isinstance(items, list):
        return payload

    truncated_payload = dict(payload)
    truncated_items = list(items)
    while count_tokens(truncated_payload, model=MODEL_NAME) > max_tokens and len(truncated_items) > 1:
        truncated_items = truncated_items[:-1]
        truncated_payload["items"] = truncated_items
    return truncated_payload


def _execute_sql_tool_call(tool_call, user_input, conversation_id, request_id, round_number):
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
            "round": round_number,
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
                "round": round_number,
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
            "message": "Nessun dato disponibile per la query richiesta."
        }
        output_json = json.dumps(output_payload, ensure_ascii=False)
    elif isinstance(query_result, list):
        max_tokens = 10000
        truncated_result = query_result[:]
        while count_tokens(truncated_result, model=MODEL_NAME) > max_tokens and len(truncated_result) > 1:
            truncated_result = truncated_result[:-1]

        is_partial = len(truncated_result) < len(query_result)
        partial_message = (
            "Nota: i risultati mostrati sono parziali. Per una lista completa, restringi la ricerca."
            if is_partial
            else "Nota: i risultati mostrati sono completi."
        )

        tool_payload = {
            "user_request": user_input,
            "report_title": "Analisi dei dati richiesti",
            "summary": "Ecco una sintesi dei dati recuperati dalla query eseguita.",
            "table_data": truncated_result,
            "conclusions": "Analizza questi dati e fornisci una valutazione dei trend e delle informazioni piu rilevanti.",
            "note": partial_message,
            "format": "JSON",
        }
        output_json = log_json_output(tool_payload)
    else:
        output_payload = {
            "value": query_result,
            "format": "scalar",
        }
        output_json = json.dumps(output_payload, ensure_ascii=False, default=convert_decimal)

    output_estimated_tokens = count_tokens({"output": output_json}, model=MODEL_NAME)
    log_conversation_event(
        conversation_id,
        "tool_output_prepared",
        request_id=request_id,
        payload={
            "round": round_number,
            "call_id": tool_call.call_id,
            "tool_name": tool_call.name,
            "output_chars": len(output_json),
            "output_estimated_tokens": output_estimated_tokens,
        },
    )
    return _build_function_call_output(tool_call.call_id, output_json)


def _execute_mcp_tool_call(tool_call, conversation_id, request_id, round_number):
    arguments = json.loads(tool_call.arguments or "{}")
    tool_error = None
    tool_result = None
    tool_start = time.perf_counter()
    try:
        tool_result = call_mcp_tool(tool_call.name, arguments)
        tool_result = _truncate_items_payload(tool_result)
    except MCPBridgeError as exc:
        tool_error = str(exc)
    except Exception as exc:
        tool_error = str(exc)
    tool_elapsed_ms = round((time.perf_counter() - tool_start) * 1000, 2)

    log_conversation_event(
        conversation_id,
        "tool_execute_mcp_completed",
        request_id=request_id,
        payload={
            "round": round_number,
            "tool_name": tool_call.name,
            "elapsed_ms": tool_elapsed_ms,
            "arguments": arguments,
            "error": tool_error,
            "result_keys": sorted(tool_result.keys()) if isinstance(tool_result, dict) else None,
        },
    )

    if tool_error:
        output_payload = {
            "message": "MCP_ERROR",
            "tool_name": tool_call.name,
            "error": tool_error,
            "arguments": arguments,
        }
        output_json = json.dumps(output_payload, ensure_ascii=False)
    else:
        output_json = json.dumps(tool_result, ensure_ascii=False, default=convert_decimal)

    output_estimated_tokens = count_tokens({"output": output_json}, model=MODEL_NAME)
    log_conversation_event(
        conversation_id,
        "tool_output_prepared",
        request_id=request_id,
        payload={
            "round": round_number,
            "call_id": tool_call.call_id,
            "tool_name": tool_call.name,
            "output_chars": len(output_json),
            "output_estimated_tokens": output_estimated_tokens,
        },
    )
    return _build_function_call_output(tool_call.call_id, output_json)


def build_tools_schema():
    tools = [
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

    try:
        tools.extend(get_openai_tool_schemas())
    except Exception as exc:
        print(f"Impossibile caricare i tool MCP: {exc}")

    return tools


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
        try:
            available_mcp_tool_names = get_mcp_tool_names()
        except Exception as exc:
            available_mcp_tool_names = set()
            log_conversation_event(
                conversation_id,
                "mcp_tools_discovery_failed",
                request_id=request_id,
                payload={"error": str(exc)},
            )

        if available_mcp_tool_names:
            instructions += (
                "\n\nTool policy update:\n"
                "- Sono disponibili tool MCP business-oriented per l'accesso ai dati aziendali.\n"
                f"- Tool MCP disponibili: {', '.join(sorted(available_mcp_tool_names))}.\n"
                "- Preferisci i tool MCP ai SQL grezzi quando coprono direttamente la richiesta.\n"
                "- Usa execute_sql_query solo come fallback se i tool MCP disponibili non bastano.\n"
            )

        instructions += (
            "\n\nFormato finale obbligatorio:\n"
            "- Rispondi con un singolo oggetto JSON valido.\n"
            "- Le sole chiavi di primo livello ammesse sono: user_request, report_title, summary, table_data, conclusions.\n"
            "- table_data deve essere una lista piatta di oggetti-riga.\n"
            "- Non usare dataset annidati, non usare rows annidate, non aggiungere altre chiavi di primo livello.\n"
        )

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
                if tool_call.name == "execute_sql_query":
                    tool_outputs.append(
                        _execute_sql_tool_call(
                            tool_call,
                            user_input=user_input,
                            conversation_id=conversation_id,
                            request_id=request_id,
                            round_number=rounds,
                        )
                    )
                    continue

                if tool_call.name in available_mcp_tool_names:
                    tool_outputs.append(
                        _execute_mcp_tool_call(
                            tool_call,
                            conversation_id=conversation_id,
                            request_id=request_id,
                            round_number=rounds,
                        )
                    )
                    continue

                log_conversation_event(
                    conversation_id,
                    "tool_call_ignored",
                    request_id=request_id,
                    payload={"round": rounds, "tool_name": tool_call.name},
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

        final_text = _normalize_final_response_json(final_text)
        _validate_final_response_semantics(final_text)

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
    except SemanticValidationError as e:
        total_elapsed_ms = round((time.perf_counter() - req_start) * 1000, 2)
        final_preview = final_text[:2000] if isinstance(locals().get("final_text"), str) else None
        log_conversation_event(
            conversation_id,
            "request_failed_semantic_validation",
            request_id=request_id,
            payload={
                "elapsed_ms": total_elapsed_ms,
                "error": str(e),
                "reason_code": _semantic_validation_reason(str(e)),
                "final_text_preview": final_preview,
            },
        )
        error_msg = "Errore tecnico momentaneo: la risposta generata non ha superato i controlli di coerenza. Riprova tra poco."
        write_message_to_json(error_msg)
        return error_msg
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
