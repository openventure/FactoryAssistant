import openai
import os
from modules.request_processing.MaketheQuery import execute_sql_query  # Import della funzione per eseguire query
from modules.visualization.test_ui import datamanger_assistant  # Import della funzione per eseguire query
import time
import json
import decimal
import datetime
import pytz
import re


# Definisci il fuso orario italiano
ITALIAN_TZ = pytz.timezone("Europe/Rome")
# Recupera la chiave API dalla variabile d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# ID dell'assistente già creato
ASSISTANT_ID = "asst_HGIP7M6ChuXTiFVhafl8QoXi"  # Sostituisci con il tuo ID se diverso
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


def write_completejsonresult(result, file):
    try:
        text_block = result[0].text.value.strip()  # 🔹 Rimuove eventuali spazi o newline in eccesso

        # 🔹 1. Controlla se il testo è racchiuso in ```json ... ```
        if text_block.startswith("```json"):
            json_match = re.search(r'```json\n(.*?)\n```', text_block, re.DOTALL)
            if json_match:
                json_string = json_match.group(1)  # 🔹 Estrai solo il JSON puro
            else:
                raise ValueError("Formato della risposta non valido. JSON non trovato.")
        else:
            json_string = text_block  # 🔹 Il testo è già un JSON valido, lo usiamo direttamente

        try:
            # 🔹 2. Converte la stringa JSON in un oggetto Python
            json_data = json.loads(json_string)
        except json.JSONDecodeError as e:
            raise ValueError(f"Errore nella conversione del JSON: {e}")

        # 🔹 3. Salva il JSON in un file
        file_path = file
        with open(file_path, "w", encoding="utf-8") as json_file:
            json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        print(f"✅ JSON salvato con successo in '{file_path}'")
    except Exception as e:
           return f"Errore nella trascrizione del JSON: {str(e)}"

def ask_assistant(user_input, thread_id=None):
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
        while wait_time < max_wait_time:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            print(f"Stato attuale: {run_status.status}")  # Debugging

            if run_status.status == "completed":
                break
            elif run_status.status in ["failed", "expired", "cancelled"]:
                messages = openai.beta.threads.messages.list(thread_id=thread_id)
                for msg in messages.data:
                    print(f"🔹 Messaggio ricevuto dall'assistente: {msg.role} - {msg.content}")
                error_details = run_status.incomplete_details if hasattr(run_status, "incomplete_details") else "Nessun dettaglio disponibile"
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
                                # 🔹 Limita il numero di risultati a 50 per sicurezza
                                max_results =75
                                if query_result:
                                    is_partial = len(query_result) > max_results  # Controlla se il dataset è stato troncato
                                else:
                                    is_partial = False

                                if isinstance(query_result, list) and is_partial:
                                    query_result = query_result[:max_results]  # 🔥 Troncatura
                                    # 🔹 Costruisci il messaggio per informare l'utente
                                    partial_message = "⚠️ Nota: I risultati mostrati sono parziali. Per una lista completa, restringi la ricerca." if is_partial else ""
                                else:
                                    partial_message = "⚠️ Nota: I risultati mostrati sono completi"
                                print(f"📊 Risultato ottenuto dalla query: {query_result}")

                                response = openai.beta.threads.runs.submit_tool_outputs(
                                    thread_id=thread_id,
                                    run_id=run.id,
                                    tool_outputs=[{
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({
                                            "user_request": user_input,  # Richiesta originale dell'utente
                                            "report_title": "Analisi dei dati richiesti",  # Titolo generico che può essere adattato
                                            "summary": "Ecco una sintesi dei dati recuperati dalla query eseguita.",  # Sommario iniziale
                                            "table_data": query_result,  # I dati ottenuti in formato tabellare
                                            "conclusions": "Analizza questi dati e fornisci una valutazione dei trend e delle informazioni più rilevanti.",
                                            "format": "JSON"  # 🔥 Specifica il formato
                                        }, default=convert_decimal)
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
                                        messages = openai.beta.threads.messages.list(thread_id=thread_id)
                                        for msg in messages.data:
                                            print(f"🔹 Messaggio ricevuto dall'assistente: {msg.role} - {msg.content}")
                                        error_details = run_status.incomplete_details if hasattr(run_status, "incomplete_details") else "Nessun dettaglio disponibile"
                                        return f"Errore: Il processo è terminato con stato {run_status.status}. Dettagli: {error_details}"
    
                                    time.sleep(2)  # Aspetta 2 secondi prima di riprovare
                                    wait_time += 2

                                # ✅ Ora possiamo recuperare la risposta finale dell'assistente
                                messages = openai.beta.threads.messages.list(thread_id=thread_id)
                                last_message = messages.data[0].content  # Prende l'ultimo messaggio dell'assistente
                                #Secondo Assistente
                                # write_completejsonresult(last_message, "Predata.json")
                                # request = last_message
                                # if(last_message[0].text):
                                #     request = str(last_message[0].text.value)
                                # print("Passaggio al secondo assistente")
                                
                                # result = datamanger_assistant(request)
                                write_completejsonresult(last_message, "data.json")
                                return last_message


                            except Exception as e:
                                return f"Errore nell'esecuzione della query: {str(e)}"

                else:
                    return "Errore: L'assistente è in stato 'requires_action' ma non ha fornito dettagli."


            time.sleep(2)  # Aspetta 2 secondi prima di riprovare
            wait_time += 2

        # Se supera il timeout
        if wait_time >= max_wait_time:
            return "Errore: Timeout raggiunto in attesa della risposta dall'assistente."

        # Recupera i messaggi generati dall'assistente
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        last_message = messages.data[0].content  # Prende l'ultimo messaggio dell'assistente

        return last_message
    except Exception as e:
        return f"Errore: {str(e)}"

if __name__ == "__main__":
    print("💬 Assistente attivo. Scrivi la tua richiesta o digita 'stop' per terminare.\n")
    
    # 🔹 Crea un thread una sola volta all'inizio della sessione
    thread = openai.beta.threads.create()
    thread_id = thread.id

    while True:
        user_query = input("📝 Inserisci la richiesta: ")
        if user_query.lower() == "stop":
            print("👋 Chiusura assistente. Arrivederci!")
            break  # 🔚 Esce dal loop se l'utente digita "stop"

        response = ask_assistant(user_query, thread_id=thread_id)

        print("\n🔹 Risposta dell'assistente:")
        print(response[0].text.value)
"""
input utilizzati in debug/sviluppo:
Vorrei sapere il numero di pallet prodotti nel mese corrente
    vorrei il numero pallet prodotti per mese nell'anno 2024
Vorrei sapere per ogni formato quale è la giagenza e la disponibilità
    vorrei sapere giacenza e disponibilità a 30 giorni
    vorrei sapere quanti articoli sono sottoscorta per formato
    vorrei sapere per il formato 60x60 quali articoli sono sottoscorta
Dammi gli articoli che devo produrre per ripristinare il magazzino del formato 81x81
Mi potresti dare la quantità disponibile in magazzino per ogni formato?
Vorrei sapere quante prove di assorbimento abbiamo fatto quest'anno
vorrei informazioni sull'andamento del valore degli assorbimenti degli ultimi 3 mesi
"""