# Funzioni per la registrazione e trascrizione audio
import sounddevice as sd
import speech_recognition as sr
import numpy as np
import scipy.io.wavfile as wav
import pyaudio
import openai
import pygame
import time
import os

FREQ = 44100
OUTPUT_FILE = "audio.wav"
COMANDO_TRIGGER = "diana"
SUONO_INIZIO = "recording-start.wav"
SUONO_FINE = "recording-end.wav"

# Inizializza OpenAI
API_KEY = os.getenv('OPENAI_API_KEY')
client = openai.OpenAI(api_key=API_KEY)

def riproduci_suono(file):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():  # Aspetta la fine del suono
            continue
    except Exception as e:
        print(f"⚠ Errore nella riproduzione del suono: {e}")

def ascolta_comando():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 2.0  # Attende più tempo prima di terminare l'ascolto

    with sr.Microphone() as source:
        print("Aspetto il comando vocale...")
        recognizer.adjust_for_ambient_noise(source, duration=3)  # Migliora la qualità
        try:
            audio = recognizer.listen(source)  # Ascolta
            comando = recognizer.recognize_google(audio, language="it-IT").lower()  # Converti in testo
            print(f"Hai detto: {comando}")
            return comando
        except sr.UnknownValueError:
            print("? Non ho capito il comando.")
            return None
        except sr.RequestError:
            print("? Errore con il servizio di riconoscimento.")
            return None

def registra_audio():
    recognizer = sr.Recognizer()
    with sr.Microphone(sample_rate=FREQ) as source:
        recognizer.adjust_for_ambient_noise(source)  # Adatta al rumore di fondo
        riproduci_suono(SUONO_INIZIO)  # Suono di inizio
        print("🎙 Inizio registrazione... Parla ora.")

        recognizer.pause_threshold = 3.0  # Attendere 1 secondo di silenzio prima di interrompere
        recognizer.energy_threshold = 400
        # Registra fino a quando rileva voce
        audio = recognizer.listen(source, timeout=None)  # Nessun tempo massimo

        print("✅ Registrazione completata.")
        riproduci_suono(SUONO_FINE)  # Suono di fine

        # Salva l'audio in un file WAV
        with open(OUTPUT_FILE, "wb") as f:
            f.write(audio.get_wav_data())

def trascrivi_audio():
    with open(OUTPUT_FILE, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
            language="it"  # Forza la trascrizione in italiano
        )
    return transcription

if __name__ == "__main__":
    # Loop di ascolto continuo
    while True:
        comando = ascolta_comando()
        if comando and COMANDO_TRIGGER in comando:
            print("Comando riconosciuto! Avvio la registrazione...")
            registra_audio()
            testo_trascritto = trascrivi_audio()
            print("Testo trascritto:", testo_trascritto)