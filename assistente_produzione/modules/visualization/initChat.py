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
from assistente_produzione.modules.visualization.gamma_client import (
    GammaAPIError,
    get_generation_status,
    start_generation_and_wait,
)


def _build_smart_chart(df):
    if df.empty or len(df) <= 1:
        return None

    chart_df = df.copy()
    time_hints = ("data", "date", "giorno", "day", "mese", "month", "anno", "year", "ora", "hour", "timestamp")
    label_hints = ("linea", "line", "article", "articolo", "article_code", "codice", "code", "formato", "serie", "tono", "deposito")
    primary_metric_hints = (
        "total_m2", "giacenza", "disponibilita", "shortage", "avg_m2_per_production_day",
        "avg_m2_per_calendar_day", "avg_m2", "total", "totale", "volume", "mq", "m2"
    )
    support_metric_hints = ("days", "giorni", "day", "pieces", "pezzi", "pallet", "count", "conteggio")

    for column in chart_df.columns:
        lowered = str(column).strip().lower()
        if any(hint in lowered for hint in time_hints):
            parsed = pd.to_datetime(chart_df[column], errors='coerce', dayfirst=True)
            if parsed.notna().sum() >= max(2, int(max(chart_df[column].notna().sum(), 1) * 0.6)):
                chart_df[column] = parsed

    numeric_columns = chart_df.select_dtypes(include=['number']).columns.tolist()
    datetime_columns = chart_df.select_dtypes(include=['datetime', 'datetimetz']).columns.tolist()
    categorical_columns = chart_df.select_dtypes(include=['object', 'category']).columns.tolist()

    if not numeric_columns:
        return None

    def _score_label(column_name):
        lowered = str(column_name).strip().lower()
        series = chart_df[column_name].dropna()
        unique_count = int(series.nunique()) if not series.empty else 0
        score = 0
        if any(hint in lowered for hint in label_hints):
            score += 8
        if 2 <= unique_count <= max(len(chart_df), 2):
            score += 3
        if unique_count == len(chart_df):
            score += 2
        if not series.empty:
            avg_len = float(series.astype(str).str.len().mean())
            if avg_len > 40:
                score -= 2
        return score

    def _score_metric(column_name):
        lowered = str(column_name).strip().lower()
        series = chart_df[column_name].dropna()
        unique_count = int(series.nunique()) if not series.empty else 0
        score = 0
        if any(hint in lowered for hint in primary_metric_hints):
            score += 8
        if any(hint in lowered for hint in support_metric_hints):
            score -= 3
        if unique_count <= 1:
            score -= 5
        return score

    best_metric = sorted(numeric_columns, key=_score_metric, reverse=True)[0]
    best_label = None
    if categorical_columns:
        best_label = sorted(categorical_columns, key=_score_label, reverse=True)[0]

    if best_label and _score_label(best_label) > 0:
        plot_df = chart_df[[best_label, best_metric]].dropna(subset=[best_label, best_metric])
        if len(plot_df) >= 2:
            plot_df = plot_df.sort_values(best_metric, ascending=True).tail(15)
            return px.bar(
                plot_df,
                x=best_metric,
                y=best_label,
                orientation='h',
                template='plotly_white',
            )

    if len(datetime_columns) == 1:
        time_column = datetime_columns[0]
        plot_df = chart_df[[time_column, best_metric]].dropna(subset=[time_column, best_metric]).sort_values(time_column)
        if len(plot_df) >= 2:
            fig = px.line(plot_df, x=time_column, y=best_metric, template='plotly_white')
            fig.update_traces(mode='lines+markers', marker=dict(size=6))
            return fig

    if len(numeric_columns) >= 2:
        comparable_metric = sorted(
            [col for col in numeric_columns if col != best_metric],
            key=_score_metric,
            reverse=True,
        )[0]
        plot_df = chart_df[[best_metric, comparable_metric]].dropna()
        if len(plot_df) >= 3:
            return px.scatter(plot_df, x=best_metric, y=comparable_metric, template='plotly_white')

    return None


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


def _get_report_fingerprint(report_payload):
    try:
        raw = json.dumps(report_payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(report_payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _render_gamma_panel(report_payload):
    st.subheader("🌐 Render su Gamma")

    gamma_api_key = os.getenv("GAMMA_API_KEY", "").strip()
    default_template_id = os.getenv("GAMMA_TEMPLATE_ID", "").strip()
    if "gamma_template_id" not in st.session_state:
        st.session_state.gamma_template_id = default_template_id

    st.caption("Variabili richieste: GAMMA_API_KEY e GAMMA_TEMPLATE_ID")
    template_id = st.text_input(
        "Template ID Gamma",
        value=st.session_state.gamma_template_id,
        key="gamma_template_input",
    ).strip()
    st.session_state.gamma_template_id = template_id

    if not gamma_api_key:
        st.warning("⚠️ GAMMA_API_KEY mancante: non posso inviare il JSON a Gamma.")
        return

    report_hash = _get_report_fingerprint(report_payload)
    state_key = f"gamma_generation_{report_hash}"

    col_generate, col_refresh = st.columns([1.2, 1])
    with col_generate:
        generate_clicked = st.button(
            "🚀 Genera pagina su Gamma",
            key=f"gamma_generate_{report_hash}",
            use_container_width=True,
            disabled=not template_id,
        )

    with col_refresh:
        refresh_clicked = st.button(
            "🔄 Aggiorna stato",
            key=f"gamma_refresh_{report_hash}",
            use_container_width=True,
            disabled=state_key not in st.session_state,
        )

    if generate_clicked:
        try:
            with st.spinner("Invio del JSON a Gamma e attesa rendering..."):
                generation_data = start_generation_and_wait(
                    report_payload,
                    api_key=gamma_api_key,
                    template_id=template_id,
                    timeout_sec=150,
                    poll_seconds=4,
                )
            st.session_state[state_key] = generation_data
        except GammaAPIError as ex:
            st.error(f"❌ Errore Gamma: {ex}")

    if refresh_clicked:
        current = st.session_state.get(state_key)
        generation_id = current.get("generation_id") if isinstance(current, dict) else None
        if generation_id:
            try:
                refreshed = get_generation_status(generation_id, api_key=gamma_api_key)
                refreshed["creation"] = current.get("creation")
                st.session_state[state_key] = refreshed
            except GammaAPIError as ex:
                st.error(f"❌ Errore aggiornamento Gamma: {ex}")

    generation_data = st.session_state.get(state_key)
    if not generation_data:
        return

    status = generation_data.get("status", "unknown")
    generation_id = generation_data.get("generation_id", "-")
    st.info(f"Stato Gamma: {status} | generationId: {generation_id}")

    gamma_url = generation_data.get("gamma_url")
    output_file_url = generation_data.get("output_file_url")

    if gamma_url:
        st.link_button("Apri pagina renderizzata", gamma_url)
    if output_file_url:
        st.link_button("Scarica export", output_file_url)

    with st.expander("Debug risposta Gamma", expanded=False):
        st.json(generation_data.get("raw", {}))

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
                    
            
                        fig = _build_smart_chart(df)
                        if fig is not None:
                            st.subheader("?? Visualizzazione Grafica")
                            fig.update_layout(
                                margin=dict(l=10, r=10, t=20, b=10),
                                paper_bgcolor="white",
                                plot_bgcolor="white",
                                font_color="#1A202C",
                                legend_title_text="",
                            )
                            fig.update_xaxes(showgrid=True, gridcolor="#E2E8F0", zeroline=False)
                            fig.update_yaxes(showgrid=True, gridcolor="#E2E8F0", zeroline=False)
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("?? Nessun dato numerico disponibile per il grafico.")
                    else:
                        st.warning("⚠️ Nessun dato tabellare disponibile.")

                    st.subheader("📌 Conclusioni")
                    st.write(report.conclusions)
                    st.divider()
                    _render_gamma_panel(data)
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

