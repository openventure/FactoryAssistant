from itertools import count
import time
import debugpy
import sys
import os
import streamlit as st
from uuid import uuid4
import json
import pandas as pd
import plotly.express as px
from datetime import datetime
from openai import OpenAI
import hashlib
import openai
from pathlib import Path
PYTHONPATH = os.getenv("PYTHONPATH", "")
OPENAI_API_KEY= os.getenv("OPENAI_API_KEY", "")
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() == "true"
print(f"hey!....{DEBUG_MODE} - {PYTHONPATH} ->apikey={OPENAI_API_KEY}")
if DEBUG_MODE:
    
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", 5678))
        print("🔍 Debugger in attesa di connessione....")
        debugpy.wait_for_client()
        
        print("✅ Debugger connesso, avvio Streamlit!")
    except RuntimeError as ex:
        print("✅ Debugger error, maybe yet called listen: ")


from assistente_produzione.modules.request_processing.AssistantLib import handle_request, write_text_to_json, log_conversation_event
from assistente_produzione.modules.visualization.report_contract import normalize_report_payload


def read_conversation_log_tail(conversation_id, max_lines=120):
    log_file = Path(__file__).resolve().parents[2] / "logs" / "conversations" / f"{conversation_id}.log"
    if not log_file.exists():
        return None, "Nessun log disponibile per questa conversazione."

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return log_file, "".join(tail)


def transcribe_streamlit_audio(audio_file):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OPENAI_API_KEY non configurata: impossibile trascrivere il vocale.")
        return None

    try:
        client = OpenAI(api_key=api_key)
        audio_file.seek(0)
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=("streamlit_audio.wav", audio_file.getvalue(), audio_file.type or "audio/wav"),
            response_format="text",
            language="it"
        )
        return transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
    except Exception as e:
        st.error(f"❌ Errore durante la trascrizione vocale: {e}")
        return None

def doLayout(data):
    try:
        message = data.get("message", "")
        report_keys = {"table_data", "report_title", "summary", "conclusions", "user_request", "format"}
        has_report_content = any(key in data for key in report_keys)
        if "text" in data:
            text = data.get("text", "")
            st.write(text)
            data = {"Feedback": "True"}
            
        elif "Feedback" not in data:
            if has_report_content:
                graphic_displayed = True
                after_done = True  # Attiviamo la flag per il messaggio successivo

                parse_result = normalize_report_payload(data)
                report = parse_result.report

                # 🔹 3. Visualizza il report
                with placeholder.container():
                    if not parse_result.is_valid:
                        st.warning("⚠️ Risposta parzialmente non conforme allo schema: applicati fallback automatici.")
                        with st.expander("Dettaglio errori schema"):
                            st.write(parse_result.errors)

                    st.write("⌨️ Premi Ctrl+I per avviare la registrazione...")
                    st.subheader(f"📌 {report.report_title}")
                    st.write(f"🔎 **Analisi:** {report.summary}")
                    if message:
                        st.info(message)
                    with st.expander("JSON risposta (debug)"):
                        st.json(data)
                    table_data = report.table_data

                    if table_data:
                        df = pd.DataFrame(table_data)
                        st.subheader("📋 Dati Tabellari")
                        if 'laboratorydata_ptr_id' in df.columns:
                           df.drop('laboratorydata_ptr_id', axis=1, inplace=True)
                        st.dataframe(df)
                    
            
                        numeric_columns = df.select_dtypes(include=['number']).columns
                        if len(numeric_columns) > 0 and len(df) > 1:
                            colonne_numeriche = df.select_dtypes(include=['number']).columns.tolist()
                            colonne_categoriche = df.select_dtypes(include=['object', 'category']).columns.tolist()
                            header_temporali = ['Data','data','Anno', 'anno','Mese', 'mese', 'Giorno', 'giorno']
                            colonne_datetime = df.select_dtypes(include=['datetime']).columns.tolist()
                            colonne_header = [col for col in header_temporali if col in df.columns]
                            colonne_date = list(set(colonne_datetime + colonne_header))
                            # una colonna potrebbe essere in entrambe le liste
                            colonne_numeriche = [c for c in colonne_numeriche if c not in colonne_date]
                            st.subheader("📈 Visualizzazione Grafica")
                            if len(colonne_numeriche) >= 1 and len(colonne_date) == 1:
                                # Grafico a linee
                                df_sorted = df.sort_values(by=colonne_date[0])
                                fig = px.line(df, df_sorted[colonne_date[0]], df_sorted[colonne_numeriche[0]])
                                fig.update_traces(mode='lines+markers', marker=dict(size=6))
                            elif len(colonne_numeriche) == 1 and len(colonne_categoriche) >= 1:
                                # Grafico a barre
                                fig = px.bar(df, x=df[colonne_categoriche[0]], y=df[colonne_numeriche[0]])
                            elif len(colonne_numeriche) >= 2 and len(colonne_categoriche) >= 1:
                                # Grafico a dispersione
                                df_sorted = df.sort_values(by=colonne_categoriche[0])
                                fig = px.line(df, x=colonne_categoriche[0], y=colonne_numeriche)
                                fig.update_traces(mode='lines+markers', marker=dict(size=6))
                            elif len(colonne_numeriche) == 2:
                                # Grafico a dispersione
                                fig = px.scatter(df, x=df[colonne_numeriche[0]], y=df[colonne_numeriche[1]])
                            else:
                                fig = px.bar(df, x=df.columns[0], y=numeric_columns[1], text_auto=True)
                                #fig = px.pie(df, names=colonne_categoriche[0], values=colonne_numeriche[0])

                            st.plotly_chart(fig)
                        else:
                            st.warning("⚠️ Nessun dato numerico disponibile per il grafico.")
                    else:
                        st.warning("⚠️ Nessun dato tabellare disponibile.")

                    st.subheader("📌 Conclusioni")
                    st.write(report.conclusions)
            else:
                # 🔹 Normalmente, svuotiamo la dashboard e mostriamo i messaggi
                with placeholder:
                    st.write(message)
            

    except Exception as e:
        placeholder.empty()
        placeholder.error(f"❌ Errore nel caricamento dei dati: {e}")
        time.sleep(5)


if 'conversation' not in st.session_state:
    st.session_state.conversation = []
if 'selected_response' not in st.session_state:
    st.session_state.selected_response = None
if 'assistant_thread_id' not in st.session_state:
    st.session_state.assistant_thread_id = f"conv_{uuid4()}"
    log_conversation_event(st.session_state.assistant_thread_id, "conversation_started", payload={"source": "initChat_session_init"})

json_path = "data.json"
if 'input_counter' not in st.session_state:
    st.session_state.input_counter = 0

# Header controlli fisso: nuova conversazione + input vocal/text
st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlock"]:has(#sticky-controls-marker) {
        position: sticky;
        top: 0;
        z-index: 999;
        background: var(--background-color);
        padding: 0.6rem 0 0.8rem 0;
        border-bottom: 1px solid rgba(128, 128, 128, 0.35);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if 'last_audio_hash' not in st.session_state:
    st.session_state.last_audio_hash = None
if 'prefilled_request' not in st.session_state:
    st.session_state.prefilled_request = ""

with st.container():
    st.markdown('<div id="sticky-controls-marker"></div>', unsafe_allow_html=True)
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([0.9, 1.2, 2.2])

    with ctrl_col1:
        if st.button("🆕 Nuova conversazione", use_container_width=True):
            st.session_state.conversation = []
            st.session_state.selected_response = None
            st.session_state.last_request_processed = None
            st.session_state.prefilled_request = ""
            st.session_state.last_audio_hash = None
            st.session_state.input_counter += 1
            st.session_state.assistant_thread_id = f"conv_{uuid4()}"
            log_conversation_event(st.session_state.assistant_thread_id, "conversation_started", payload={"source": "initChat_new_conversation_button"})
            st.rerun(scope="app")

    with ctrl_col2:
        # Microfono nella chat: registra dal browser e precompila il testo trascritto
        audio_input = st.audio_input("🎤 Registra richiesta vocale")

    with ctrl_col3:
        # Usa una chiave dinamica basata sul contatore
        nuova_richiesta = st.text_input(
            "Nuova richiesta all'assistente:",
            key=f"input_request_{st.session_state.input_counter}",
            value=st.session_state.prefilled_request
        )

if audio_input is not None:
    audio_bytes = audio_input.getvalue()
    current_hash = hashlib.sha256(audio_bytes).hexdigest()
    if current_hash != st.session_state.last_audio_hash:
        with st.spinner("⏳ Trascrizione vocale in corso..."):
            testo_vocale = transcribe_streamlit_audio(audio_input)
        if testo_vocale:
            st.success("✅ Trascrizione completata")
            st.session_state.prefilled_request = testo_vocale
            st.session_state.last_audio_hash = current_hash
            st.session_state.input_counter += 1
            st.rerun(scope="app")


col1, col2 = st.columns([0.6, 2.4])

with col1:
    st.header("🗒️ Storico richieste")

    for idx, item in enumerate(st.session_state.conversation):
        label = f"{idx+1}. [{item['timestamp']}] {item['request']}"
        if st.button(label, key=f"request_{idx}"):
            st.session_state.selected_response = idx

with col2:
    st.header("📊 Dettaglio Risposta")
    placeholder = st.empty()
    if st.session_state.selected_response is not None:
        if st.session_state.selected_response >= 0:
            # Sto visualizzando una richiesta dallo storico
            selected_item = st.session_state.conversation[st.session_state.selected_response]
    
            # La risposta può essere stringa JSON o già oggetto dict
            if isinstance(selected_item['response'], str):
                try:
                    data = json.loads(selected_item['response'])
                except Exception:
                    st.warning("⚠️ Errore nel caricamento della risposta JSON.")
                    data = {}
            else:
                data = selected_item['response']
        else:
            # Sto visualizzando l’ultima nuova risposta salvata in data.json
            with open("data.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        doLayout(data)

    st.subheader("🧾 Log runtime conversazione")
    with st.expander("Mostra log tecnico (eventi AI/tool)", expanded=False):
        log_col1, log_col2 = st.columns([1, 1])
        with log_col1:
            max_lines = st.number_input("Righe da visualizzare", min_value=20, max_value=1000, value=120, step=20)
        with log_col2:
            st.caption(f"Conversation ID: {st.session_state.assistant_thread_id}")

        log_path, log_tail = read_conversation_log_tail(st.session_state.assistant_thread_id, int(max_lines))
        if log_path:
            st.caption(f"File log: {log_path}")
            st.text_area("Log (tail)", value=log_tail, height=260)
        else:
            st.info(log_tail)

st.divider()


# Inizializza anche la variabile di stato per evitare loop
if 'last_request_processed' not in st.session_state:
    st.session_state.last_request_processed = None

if nuova_richiesta and nuova_richiesta != st.session_state.last_request_processed:
    placeholder.write("⏳ Elaborazione in corso...")
    log_conversation_event(
        st.session_state.assistant_thread_id,
        "user_input_submitted",
        payload={"request_text": nuova_richiesta}
    )
    write_text_to_json(nuova_richiesta)
    risposta = handle_request(nuova_richiesta, thread_id=st.session_state.assistant_thread_id)

    # Salva la richiesta come già processata
    st.session_state.last_request_processed = nuova_richiesta
    st.session_state.prefilled_request = ""

    # Aggiungi la risposta alla conversazione
    #st.session_state.conversation.append({'request': nuova_richiesta, 'response': risposta})
    data = json.load(open("data.json", "r", encoding="utf-8"))
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.conversation.append({
        'request': nuova_richiesta,
        'response': data,
        'timestamp': timestamp
    })
    st.session_state.selected_response = -1 #len(st.session_state.conversation) - 1
   # Incrementa il contatore per forzare la ricreazione del widget
    st.session_state.input_counter += 1
    st.rerun(scope="app")
