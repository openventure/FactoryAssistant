import os
from modules.request_processing.MaketheQuery import execute_sql_query  # Import della funzione per eseguire query
from modules.visualization.test_ui import datamanger_assistant  # Import della funzione per eseguire query
from modules.request_processing.AssistantLib import handle_request, write_message_to_json, write_text_to_json
import modules.request_processing.AssistantLib as al
import time
import json
import decimal
import datetime
import pytz
import re
from uuid import uuid4


if __name__ == "__main__":
    print("💬 Assistente attivo. Scrivi la tua richiesta o digita 'stop' per terminare.\n")
    
    # 🔹 Crea un ID conversazione una sola volta all'inizio della sessione
    thread_id = f"conv_{uuid4()}"

    while True:
        user_query = input("📝 Inserisci la richiesta: ")
        if user_query.lower() == "stop":
            print("👋 Chiusura assistente. Arrivederci!")
            break  # 🔚 Esce dal loop se l'utente digita "stop"
        # Scrive il testo inserito dall'utente nel file di log (in modalità append)
        with open("user_query.log", "a", encoding="utf-8") as log_file:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file.write(timestamp + ": " + user_query + "\n")
        write_text_to_json(f"📝 Testo trascritto: {user_query}")
        # In modalità CLI non serve attendere un "Feedback" dal front-end Streamlit.
        # Quel valore non viene scritto su data.json e il loop resta bloccato.
        response = al.handle_request(user_query, thread_id=thread_id)

        print("\n🔹 Risposta dell'assistente:")
        if isinstance(response, list):
            print(response[0].text.value)
        else:    
            print(response)
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
