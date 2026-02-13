#Punto di ingresso principale
import time
from modules.speech_to_text.speech import ascolta_comando, registra_audio, trascrivi_audio, COMANDO_TRIGGER
from modules.request_processing.AssistantLib import handle_request, write_message_to_json, write_text_to_json
import keyboard 
import json
import datetime
from uuid import uuid4


def main():
    #write_message_to_json("🔊 Assistente in attesa di un comando...")

    # ID conversazione locale per mantenere il contesto lato applicazione
    thread_id = f"conv_{uuid4()}"
    json_path = "data.json"
    while True:
        #write_message_to_json("⌨️ Premi Ctrl+I per avviare la registrazione...")
        print("⌨️ Premi Ctrl+I per avviare la registrazione...")
        keyboard.wait("ctrl+i")  # Aspetta che l'utente prema la combinazione di tasti
        
        write_message_to_json("🎙 Combinazione riconosciuta! Avvio la registrazione...")
        registra_audio()
        
        write_message_to_json("⏳ Trascrizione dell'audio in corso...")
        testo_trascritto = trascrivi_audio()
        write_text_to_json(f"📝 Testo trascritto: {testo_trascritto}")
        # Scrive il testo inserito dall'utente nel file di log (in modalità append)
        with open("trascrizione_testo.log", "a", encoding="utf-8") as log_file:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file.write(timestamp + ": " + testo_trascritto + "\n")
        last_data = None  # Per confrontare i cambiamenti nel file JSON
        while True:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "Feedback" in data:
                break
            if data == last_data:
                time.sleep(1)
                continue
            last_data = data

        print(f"📝 Testo trascritto: {testo_trascritto}")

        if testo_trascritto:
            write_message_to_json("📡 Invio del testo all'assistente...")
            risposta = handle_request(testo_trascritto, thread_id)
            print("🤖 Risposta dell'assistente:")
            if isinstance(risposta, list):
                print(risposta[0].text.value)
            else:
                print(risposta)
        else:
            write_message_to_json("⚠️ Nessun testo trascritto, riprova.")
        
        time.sleep(2)  # Evita il polling continuo


if __name__ == "__main__":
    main()
""" con wisper behaviour
if comando and COMANDO_TRIGGER in comando:
            print("🎙 Comando riconosciuto! Avvio la registrazione...")
            registra_audio()
            
            print("⏳ Trascrizione dell'audio in corso...")
            testo_trascritto = trascrivi_audio()
            print(f"📝 Testo trascritto: {testo_trascritto}")
            
            if testo_trascritto:
                print("📡 Invio del testo all'assistente...")
                risposta = ask_assistant(testo_trascritto)
                print("🤖 Risposta dell'assistente:")
                print(risposta)
            else:
                print("⚠️ Nessun testo trascritto, riprova.")
"""

"""without wisper behaviour
if comando and comando.startswith(COMANDO_TRIGGER):
            comando_filtrato = comando[len(COMANDO_TRIGGER):].strip()
            print(f"📡 Invio del testo all'assistente: {comando_filtrato}")
            risposta = ask_assistant(comando_filtrato)
            print("🤖 Risposta dell'assistente:")
            print(risposta)
"""
"""versione senza google recognizer
        print("⌨️ Premi Ctrl+I per avviare la registrazione...")
        keyboard.wait("ctrl+i")  # Aspetta che l'utente prema la combinazione di tasti
        
        print("🎙 Combinazione riconosciuta! Avvio la registrazione...")
        registra_audio()
        
        print("⏳ Trascrizione dell'audio in corso...")
        testo_trascritto = trascrivi_audio()
        print(f"📝 Testo trascritto: {testo_trascritto}")
        
        if testo_trascritto:
            print("📡 Invio del testo all'assistente...")
            risposta = ask_assistant(testo_trascritto, thread_id)
            print("🤖 Risposta dell'assistente:")
            print(risposta)
        else:
            print("⚠️ Nessun testo trascritto, riprova.")
        
        time.sleep(2)  # Evita il polling continuo

"""