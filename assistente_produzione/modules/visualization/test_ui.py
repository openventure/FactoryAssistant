# Test unitari per il modulo
import openai
import os
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
ASSISTANT_ID = "asst_jIANvCqvyAbCZQ5k138nYYHA"  # Sostituisci con il tuo ID se diverso

def datamanger_assistant(data, thread_id=None):
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
            content=data
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
