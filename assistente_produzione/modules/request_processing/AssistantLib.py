import openai
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

# Definisci il fuso orario italiano
ITALIAN_TZ = pytz.timezone("Europe/Rome")
# Recupera la chiave API dalla variabile d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ID dell'assistente già creato
ASSISTANT_ID = "asst_HU8nHRJeOTlGMglSlByTwV0a" #"asst_AGnvzJdTlvtHtjyMaMEAPock" #<--fatto con mini | fatto con gpt-4o--> "asst_HU8nHRJeOTlGMglSlByTwV0a"  # Sostituisci con il tuo ID se diverso
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
def get_last_assistant_message(thread_id):
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    return messages.data[0] if messages.data else None
def handle_request(user_input, thread_id=None):
    """
    Invia una richiesta all'assistente e gestisce eventuali azioni richieste.
    """
    try:
        assistant = openai.beta.assistants.retrieve(ASSISTANT_ID)

        # Se non esiste un thread, creane uno nuovo (SOLO ALLA PRIMA CHIAMATA)
        if thread_id is None:
            thread = openai.beta.threads.create()
            thread_id = thread.id  # Salva l'ID del thread per le chiamate successive

        # Aggiungi un messaggio al thread esistente
        message = openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        # Esegue il run della conversazione
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant.id,
            tool_choice="auto"  # 🔥 Indica all'assistente di usare il tool automaticamente
        )

        # Attendi il completamento dell'elaborazione con timeout
        max_wait_time = 60  # Secondi massimi di attesa
        wait_time = 0
        exit_by_error = False
        while wait_time < max_wait_time:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            print(f"Stato attuale: {run_status.status}")  # Debugging

            if run_status.status == "completed":
                last_message = get_last_assistant_message(thread_id)
                write_completejsonresult(f"{last_message.content[0].text.value.strip()}")
                #write_message_to_json( f"{last_message.content[0].text.value.strip()}")
                #exit_by_error = True
                return f"Messaggio: Il processo è terminato con stato {run_status.status}. Dettagli: {last_message.content[0].text.value.strip()}"
            elif run_status.status in ["failed", "expired", "cancelled"]:
                messages = openai.beta.threads.messages.list(thread_id=thread_id)
                for msg in messages.data:
                    print(f"🔹 Messaggio ricevuto dall'assistente: {msg.role} - {msg.content}")
                error_details = run_status.incomplete_details if hasattr(run_status, "incomplete_details") else "Nessun dettaglio disponibile"
                print("⚠️ Errore rilevato, avvio di un nuovo thread...")
                new_thread = openai.beta.threads.create()
                thread_id = new_thread.id
                write_message_to_json( f"Errore: Il processo è terminato con stato {run_status.status}. Dettagli: {error_details}")
                return f"Errore: Il processo è terminato con stato {run_status.status}. Dettagli: {error_details}"
                
            elif run_status.status == "requires_action":
                # Controlla l'azione richiesta
                if hasattr(run_status, "required_action"):
                    print("⚠️ Azione richiesta (struttura oggetto):", run_status.required_action)  # Debug dettagliato

                    # Estrai manualmente i dati
                    tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                    for tool_call in tool_calls:
                        print(f"🔹 Tool chiamato: {tool_call.function.name}")
                        print(f"🔹 ID chiamata: {tool_call.id}")
                        print(f"🔹 Parametri ricevuti: {tool_call.function.arguments}")

                        if tool_call.function.name == "execute_sql_query":
                            try:
                                query_sql = json.loads(tool_call.function.arguments)["query_sql"]
                                print(f"🔹 Query estratta: {query_sql}")

                                # Esegui la query SQL
                                query_result = execute_sql_query(query_sql)
                                if not query_result:
                                    write_message_to_json("⚠️ Nessun dato disponibile per la query richiesta.")
                                    return "⚠️ Nessun dato disponibile per la query richiesta."
                                # 🔹 Limita il numero di risultati a 50 per sicurezza
                                # 🔹 Calcolo token e truncatura dinamica se serve
                                max_tokens = 10000
                                truncated_result = query_result[:]

                                while count_tokens(truncated_result) > max_tokens and len(truncated_result) > 1:
                                    truncated_result = truncated_result[:-1]  # Rimuove una riga alla volta

                                # Verifica se è stato troncato
                                is_partial = len(truncated_result) < len(query_result)
                                query_result = truncated_result  # Sostituisce con la versione tagliata

                                # 🔹 Costruisci il messaggio informativo
                                partial_message = (
                                    "⚠️ Nota: I risultati mostrati sono parziali. Per una lista completa, restringi la ricerca."
                                    if is_partial else
                                    "⚠️ Nota: I risultati mostrati sono completi"
                                )

                                print(f"📊 Risultato ottenuto dalla query ({len(query_result)} righe, {count_tokens(query_result)} token):")

                                #check and log payload
                                tool_payload = {
                                        "user_request": user_input,
                                        "report_title": "Analisi dei dati richiesti",
                                        "summary": "Ecco una sintesi dei dati recuperati dalla query eseguita.",
                                        "table_data": query_result,
                                        "conclusions": "Analizza questi dati e fornisci una valutazione dei trend e delle informazioni più rilevanti.",
                                        "format": "JSON"
                                    }
                                json_payload = log_json_output(tool_payload)  # Validazione e logging

                                response = openai.beta.threads.runs.submit_tool_outputs(
                                    thread_id=thread_id,
                                    run_id=run.id,
                                    tool_outputs=[{
                                        "tool_call_id": tool_call.id,
                                        "output": json_payload
                                    }]
                                )


                                # 🕒 Attendi che il run venga completato prima di procedere
                                max_wait_time = 60  # Tempo massimo di attesa in secondi
                                wait_time = 0
                                while wait_time < max_wait_time:
                                    run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                                    print(f"🔄 Stato attuale dopo l'invio del risultato: {run_status.status}")

                                    if run_status.status == "completed":
                                        break  # Il run è completato, possiamo proseguire
                                    elif run_status.status in ["failed", "expired", "cancelled"]:
                                        print("⚠️ Errore rilevato dopo la richiesta del tool, avvio di un nuovo thread...")
                                        messages = openai.beta.threads.messages.list(thread_id=thread_id)
                                        for msg in messages.data:
                                            print(f"🔹 Messaggio ricevuto dall'assistente: {msg.role} - {msg.content}")
                                        error_details = run_status.incomplete_details if hasattr(run_status, "incomplete_details") else "Nessun dettaglio disponibile"
                                        new_thread = openai.beta.threads.create()
                                        thread_id = new_thread.id
                                        write_message_to_json( f"Errore: Il processo è terminato dopo la richiesta del tool con stato {run_status.status}. Dettagli: {error_details}")
                                        return f"Errore: Il processo è terminato con stato {run_status.status}. Dettagli: {error_details}"
                                        
                                    time.sleep(2)  # Aspetta 2 secondi prima di riprovare
                                    wait_time += 2

                                # ✅ Ora possiamo recuperare la risposta finale dell'assistente
                                messages = openai.beta.threads.messages.list(thread_id=thread_id)
                                last_message = messages.data[0].content  # Prende l'ultimo messaggio dell'assistente
                                
                                new_json_output = replace_table_data_in_message(last_message, query_result)

                                
                                write_completejsonresult(new_json_output, "data.json")
                                return last_message


                            except Exception as e:
                                error_msg = f"❌ Errore durante l'esecuzione della query: {str(e)}"
                                print(error_msg)
                                write_message_to_json(error_msg)
                                return error_msg

                else:
                    return "Errore: L'assistente è in stato 'requires_action' ma non ha fornito dettagli."


            time.sleep(2)  # Aspetta 2 secondi prima di riprovare
            wait_time += 2

        # Se supera il timeout
        if wait_time >= max_wait_time:
            return "Errore: Timeout raggiunto in attesa della risposta dall'assistente."
        

        #if(exit_by_error):
        #   write_message_to_json(last_message[0].text.value)
        return "DO Nothing!"
    except Exception as e:
        return f"Errore: {str(e)}"


