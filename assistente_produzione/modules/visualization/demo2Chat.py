import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st
from openai import OpenAI

from assistente_produzione.modules.request_processing.AssistantLib import handle_request, log_conversation_event, write_text_to_json
from assistente_produzione.modules.visualization.gamma_client import GammaAPIError, get_generation_status, start_generation_and_wait
from assistente_produzione.modules.visualization.report_contract import normalize_report_payload

st.set_page_config(page_title="CERAMIC.AI Demo", layout="wide", initial_sidebar_state="expanded")

REPORT_KEYS = {"table_data", "report_title", "summary", "conclusions", "user_request", "format"}
POWERED_LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "assistente_produzioneassetsopenventure-powered.png"
QUICK_PROMPT_GROUPS = {
    "Stock e ordini": [
        "Quali articoli 60x120 hanno ordini superiori alla disponibilita attuale?",
        "Qual è la giacenza attuale per formato?",
        "Qual è la disponibilità reale per l'articolo 304040?",
        "Quali articoli 60x120 sono sottoscorta rispetto alla soglia minima?",
    ],
    "Produzione": [
        "Qual è la produzione giornaliera media per linea nell’ultimo mese?",
        "Quali articoli abbiamo prodotto di più negli ultimi 30 giorni?",
        "Quali formati stanno producendo più metri quadrati?",
        "Confronta la produzione di questo mese con il mese scorso.",
    ],
    "Laboratorio": [
        "Analizza le prove di laboratorio dell'ultima settimana.",
        "Relaziona il valore medio dell'assorbimento con l'orario in cui è avvenuto",
        "Dammi l'assorbimento medio degli articoli degli ultimi tre mesi",
        "Quali articoli hanno mostrato piu variabilita nelle prove di assorbimento?",        
    ],
}



def _append_report_event(report_hash, message, extra=None):
    log_key = f"report_generation_log_{report_hash}"
    if log_key not in st.session_state:
        st.session_state[log_key] = []
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": message}
    if extra is not None:
        entry["extra"] = extra
    st.session_state[log_key].append(entry)


def _get_report_events(report_hash):
    return st.session_state.get(f"report_generation_log_{report_hash}", [])


def inject_demo_styles():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');

        :root {
            --primary: #004E98;
            --primary-strong: #003E79;
            --surface: #FFFFFF;
            --background: #F4F5F7;
            --border: #E2E8F0;
            --text: #1A202C;
            --muted: #64748B;
            --ok: #2E7D32;
        }

        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', sans-serif;
        }

        .stApp {
            background:
                linear-gradient(rgba(244, 245, 247, 0.97), rgba(244, 245, 247, 0.97)),
                linear-gradient(to right, rgba(26, 32, 44, 0.04) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(26, 32, 44, 0.04) 1px, transparent 1px);
            background-size: auto, 36px 36px, 36px 36px;
            color: var(--text);
        }

        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1380px;
        }

        section[data-testid="stSidebar"] {
            background: var(--surface);
            border-right: 1px solid var(--border);
            width: 280px !important;
            min-width: 280px !important;
        }

        section[data-testid="stSidebar"] .block-container {
            padding: 1rem;
        }

        .brand-box {
            border: 1px solid var(--border);
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            padding: 1rem;
            margin-bottom: 1rem;
        }

        .brand-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            margin: 0;
        }

        .brand-subtitle, .mono-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.68rem;
            color: var(--muted);
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        .empty-history, .hero-box, .summary-box {
            border: 1px solid var(--border);
            background: var(--surface);
            box-shadow: 0 18px 35px rgba(15, 23, 42, 0.04);
        }

        .empty-history {
            padding: 0.95rem;
            color: var(--muted);
            font-size: 0.84rem;
            line-height: 1.6;
        }

        .hero-box {
            padding: 2.4rem 2rem;
            text-align: center;
            margin-top: 2rem;
        }

        .hero-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: clamp(2rem, 3.5vw, 3.3rem);
            letter-spacing: -0.04em;
            margin: 0.4rem 0 0.8rem 0;
        }

        .hero-copy {
            max-width: 760px;
            margin: 0 auto;
            color: var(--muted);
            line-height: 1.7;
        }

        .top-status {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 0.65rem;
            margin-bottom: 0.8rem;
            color: var(--muted);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .status-dot {
            width: 0.52rem;
            height: 0.52rem;
            border-radius: 999px;
            background: var(--ok);
            box-shadow: 0 0 0 5px rgba(46, 125, 50, 0.12);
            display: inline-block;
        }

        .section-card {
            border: 1px solid var(--border);
            background: var(--surface);
            box-shadow: 0 18px 35px rgba(15, 23, 42, 0.04);
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }

        .section-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }

        div[data-testid="stTextInput"] input {
            border-radius: 2px;
            border: 1px solid var(--border);
            min-height: 3.1rem;
            background: var(--surface);
            color: var(--text);
            box-shadow: none;
        }

        div[data-testid="stTextInput"] input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 1px var(--primary);
        }

        .stButton > button, div[data-testid="stAudioInput"] button {
            border-radius: 2px;
            border: 1px solid var(--border);
            background: var(--surface);
            color: var(--text);
            box-shadow: none;
        }

        .stButton > button:hover, div[data-testid="stAudioInput"] button:hover {
            border-color: var(--primary);
            color: var(--primary);
        }

        .stButton > button[kind="primary"] {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }

        .stButton > button[kind="primary"]:hover {
            background: var(--primary-strong);
            border-color: var(--primary-strong);
            color: white;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
        }

        div[data-testid="stPlotlyChart"] {
            border: 1px solid var(--border);
            background: var(--surface);
            padding: 0.4rem;
        }

        div[data-testid="stPlotlyChart"] .js-plotly-plot .plotly text {
            fill: var(--text) !important;
        }

        div[data-testid="stPlotlyChart"] .js-plotly-plot .plotly .modebar-btn svg {
            fill: var(--muted) !important;
        }

        .chart-empty-state {
            border: 1px dashed var(--border);
            background: #F8FAFC;
            color: var(--text);
            padding: 0.9rem 1rem;
            margin-bottom: 1rem;
            line-height: 1.6;
        }

        .chart-empty-state strong {
            display: block;
            margin-bottom: 0.2rem;
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.96rem;
        }

        div[data-testid="stAlert"], .stAlert, div[data-baseweb="notification"] {
            background: #F8FAFC !important;
            color: var(--text) !important;
            border: 1px solid var(--border) !important;
        }

        div[data-testid="stAlert"] *, .stAlert *, div[data-baseweb="notification"] * {
            color: var(--text) !important;
        }

        div[data-testid="stExpander"] details {
            border: 1px solid var(--border);
            background: var(--surface);
        }

        div[data-testid="stExpander"] summary {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .powered-footer {
            margin-top: 1.1rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }

        .powered-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.64rem;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-top: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def read_conversation_log_tail(conversation_id, max_lines=120):
    log_file = Path(__file__).resolve().parents[2] / "logs" / "conversations" / f"{conversation_id}.log"
    if not log_file.exists():
        return None, "Nessun log disponibile per questa conversazione."
    with open(log_file, "r", encoding="utf-8") as file_handle:
        lines = file_handle.readlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return log_file, "".join(tail)


def transcribe_streamlit_audio(audio_file):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY non configurata: impossibile trascrivere il vocale.")
        return None
    try:
        client = OpenAI(api_key=api_key)
        audio_file.seek(0)
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=("streamlit_audio.wav", audio_file.getvalue(), audio_file.type or "audio/wav"),
            response_format="text",
            language="it",
        )
        return transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
    except Exception as exc:
        st.error(f"Errore durante la trascrizione vocale: {exc}")
        return None


def _get_report_fingerprint(report_payload):
    try:
        raw = json.dumps(report_payload, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(report_payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _render_detailed_report_panel(report_payload):
    st.markdown("<div class='section-card'><div class='section-title'>Report dettagliato</div><div class='mono-label'>Documento esteso generato a partire dall'analisi corrente</div></div>", unsafe_allow_html=True)
    gamma_api_key = os.getenv("GAMMA_API_KEY", "").strip()
    template_id = os.getenv("GAMMA_TEMPLATE_ID", "").strip()
    if not gamma_api_key or not template_id:
        st.info("La funzione di report dettagliato non e disponibile in questo ambiente.")
        return

    report_hash = _get_report_fingerprint(report_payload)
    state_key = f"gamma_generation_{report_hash}"

    col_generate, col_refresh = st.columns([1.2, 1])
    with col_generate:
        generate_clicked = st.button(
            "Genera report dettagliato",
            key=f"gamma_generate_{report_hash}",
            use_container_width=True,
        )
    with col_refresh:
        refresh_clicked = st.button(
            "Aggiorna stato report",
            key=f"gamma_refresh_{report_hash}",
            use_container_width=True,
            disabled=state_key not in st.session_state,
        )

    if generate_clicked:
        try:
            with st.spinner("Generazione del report dettagliato in corso..."):
                generation_data = start_generation_and_wait(
                    report_payload,
                    api_key=gamma_api_key,
                    template_id=template_id,
                    timeout_sec=150,
                    poll_seconds=4,
                )
            st.session_state[state_key] = generation_data
            _append_report_event(report_hash, "Report dettagliato generato o aggiornato dopo l'attesa.", {"generation_id": generation_data.get("generation_id"), "status": generation_data.get("status")})
        except GammaAPIError as exc:
            _append_report_event(report_hash, "Errore nella generazione del report.", {"error": str(exc)})
            st.error(f"Errore nella generazione del report: {exc}")

    if refresh_clicked:
        current = st.session_state.get(state_key)
        generation_id = current.get("generation_id") if isinstance(current, dict) else None
        if generation_id:
            try:
                refreshed = get_generation_status(generation_id, api_key=gamma_api_key)
                refreshed["creation"] = current.get("creation")
                st.session_state[state_key] = refreshed
                _append_report_event(report_hash, "Stato report aggiornato manualmente.", {"status": refreshed.get("status"), "generation_id": generation_id})
            except GammaAPIError as exc:
                _append_report_event(report_hash, "Errore aggiornamento stato report.", {"error": str(exc), "generation_id": generation_id})
                st.error(f"Errore aggiornamento report: {exc}")

    generation_data = st.session_state.get(state_key)
    if not generation_data:
        return

    status = generation_data.get("status", "unknown")
    generation_id = generation_data.get("generation_id", "-")
    st.info(f"Stato report: {status} | id: {generation_id}")

    action_col1, action_col2 = st.columns([1, 1])
    with action_col1:
        if generation_data.get("gamma_url"):
            st.link_button("Apri report dettagliato", generation_data["gamma_url"], use_container_width=True)
    with action_col2:
        if generation_data.get("output_file_url"):
            st.link_button("Scarica report", generation_data["output_file_url"], use_container_width=True)

    with st.expander("Log richiesta report", expanded=False):
        events = _get_report_events(report_hash)
        if events:
            for event in events[::-1]:
                st.write(f"[{event['time']}] {event['message']}")
                if event.get("extra"):
                    st.caption(json.dumps(event["extra"], ensure_ascii=False))
        else:
            st.caption("Nessun evento registrato.")

    with st.expander("Dettagli tecnici report", expanded=False):
        st.json({
            "state": generation_data,
            "events": _get_report_events(report_hash),
        })


def render_chart(df):
    if df.empty or len(df) <= 1:
        return None

    time_hints = ("data", "date", "giorno", "day", "mese", "month", "anno", "year", "ora", "hour", "timestamp")
    id_hints = ("id", "codice", "code", "codeart", "ptr", "uuid", "guid")
    description_hints = ("descr", "description", "desc", "toni", "note", "comment")
    group_hints = ("serie", "formato", "linea", "line", "tono", "reparto", "categoria", "family")
    support_hints = ("count", "conteggio", "numero", "num_", "n_", "n.", "prove", "records", "righe")
    metric_hints = (
        "shortage", "delta", "scost", "diff", "media", "avg", "mean", "tot", "total",
        "assorb", "giac", "consegn", "produz", "stock", "disp", "valore", "m2", "mq",
        "perc", "percent", "ratio", "indice", "volume",
    )
    priority_metric_hints = ("shortage", "delta", "scost", "diff", "gap", "backlog")

    def _lower_name(column_name):
        return str(column_name).strip().lower()

    def _contains_hint(column_name, hints):
        lowered = _lower_name(column_name)
        return any(hint in lowered for hint in hints)

    def _normalized_tokens(column_name):
        return [token for token in re.split(r"[^a-z0-9]+", _lower_name(column_name)) if token]

    def _metric_unit(column_name):
        tokens = _normalized_tokens(column_name)
        unit_tokens = {"m2", "mq", "perc", "percent", "kg", "tons", "ton", "ore", "hours"}
        for token in reversed(tokens):
            if token in unit_tokens:
                return token
        return tokens[-1] if tokens else ""

    def _is_datetime_candidate(column_name, series):
        if pd.api.types.is_datetime64_any_dtype(series):
            return True
        if not _contains_hint(column_name, time_hints):
            return False
        parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
        valid_count = int(parsed.notna().sum())
        return valid_count >= max(2, int(max(series.notna().sum(), 1) * 0.6))

    def _normalize_chart_df(source_df):
        chart_df = source_df.copy()
        for column in chart_df.columns:
            if _is_datetime_candidate(column, chart_df[column]):
                parsed = pd.to_datetime(chart_df[column], errors="coerce", dayfirst=True)
                if parsed.notna().sum() >= 2:
                    chart_df[column] = parsed
        return chart_df

    def _profile_columns(chart_df):
        profiles = []
        row_count = max(len(chart_df), 1)
        for column in chart_df.columns:
            series = chart_df[column]
            non_null = series.dropna()
            unique_count = int(non_null.nunique()) if not non_null.empty else 0
            unique_ratio = unique_count / max(len(non_null), 1)
            avg_text_length = 0.0
            if not non_null.empty and (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
                avg_text_length = float(non_null.astype(str).str.len().mean())

            is_numeric = pd.api.types.is_numeric_dtype(series)
            is_datetime = pd.api.types.is_datetime64_any_dtype(series)
            is_code_like = _contains_hint(column, id_hints)
            is_description_like = _contains_hint(column, description_hints)
            is_group_like = _contains_hint(column, group_hints)
            is_support_metric = is_numeric and _contains_hint(column, support_hints)
            is_priority_metric = is_numeric and _contains_hint(column, priority_metric_hints)
            metric_score = 0
            label_score = 0
            group_score = 0

            if is_numeric:
                metric_score += 2
                if _contains_hint(column, metric_hints):
                    metric_score += 2
                if is_priority_metric:
                    metric_score += 4
                if unique_count <= 1:
                    metric_score -= 4
                if is_code_like and unique_ratio > 0.9:
                    metric_score -= 6
                if is_support_metric:
                    metric_score -= 2
            elif not is_datetime and unique_count > 1:
                if is_description_like and avg_text_length <= 42 and unique_ratio >= 0.45:
                    label_score += 3
                if is_code_like and unique_ratio >= 0.45:
                    label_score += 2
                if not is_code_like and not is_description_like and unique_ratio >= 0.6 and avg_text_length <= 32:
                    label_score += 2
                if avg_text_length > 60:
                    label_score -= 4
                elif avg_text_length > 42:
                    label_score -= 2

                if is_group_like:
                    group_score += 3
                if 2 <= unique_count <= 8:
                    group_score += 2
                elif 9 <= unique_count <= 15:
                    group_score += 1
                elif unique_count > 20:
                    group_score -= 3
                if is_code_like:
                    group_score -= 3
                if is_description_like and avg_text_length > 35:
                    group_score -= 2

            profiles.append({
                "name": column,
                "unique_count": unique_count,
                "unique_ratio": unique_ratio,
                "is_numeric": is_numeric,
                "is_datetime": is_datetime,
                "is_support_metric": is_support_metric,
                "is_priority_metric": is_priority_metric,
                "metric_score": metric_score,
                "label_score": label_score,
                "group_score": group_score,
                "row_coverage": int(non_null.shape[0]) / row_count,
            })
        return profiles

    def _best_metric(metric_profiles):
        if not metric_profiles:
            return None
        return sorted(
            metric_profiles,
            key=lambda item: (
                item["is_priority_metric"],
                item["metric_score"],
                item["row_coverage"],
                item["unique_count"],
            ),
            reverse=True,
        )[0]

    def _select_line_metrics(metric_profiles):
        primary_metrics = [item for item in metric_profiles if not item["is_support_metric"]]
        if not primary_metrics:
            return []
        primary_metrics = sorted(primary_metrics, key=lambda item: (item["is_priority_metric"], item["metric_score"]), reverse=True)
        selected = [primary_metrics[0]["name"]]
        for candidate in primary_metrics[1:]:
            if candidate["name"] == selected[0]:
                continue
            if _metric_unit(candidate["name"]) == _metric_unit(selected[0]):
                selected.append(candidate["name"])
                break
        return selected

    def _select_label_column(label_profiles):
        if not label_profiles:
            return None
        for candidate in sorted(label_profiles, key=lambda item: (item["label_score"], item["row_coverage"], item["unique_ratio"]), reverse=True):
            if candidate["unique_count"] >= 2:
                return candidate
        return None

    def _select_color_column(group_profiles, excluded_name):
        candidates = [item for item in group_profiles if item["name"] != excluded_name and 2 <= item["unique_count"] <= 8]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item["group_score"], item["row_coverage"]), reverse=True)[0]

    def _hover_columns(chart_df, excluded_columns):
        hover_columns = []
        for column in chart_df.columns:
            if column in excluded_columns:
                continue
            if pd.api.types.is_numeric_dtype(chart_df[column]):
                hover_columns.append(column)
                continue
            if _contains_hint(column, description_hints) or _contains_hint(column, group_hints):
                hover_columns.append(column)
        return hover_columns[:5]

    def _build_chart_spec(chart_df):
        profiles = _profile_columns(chart_df)
        metric_profiles = [item for item in profiles if item["is_numeric"] and item["metric_score"] > 0 and item["unique_count"] > 1]
        if not metric_profiles:
            return None

        time_profiles = [item for item in profiles if item["is_datetime"] and item["unique_count"] > 1]
        label_profiles = [item for item in profiles if not item["is_numeric"] and not item["is_datetime"] and item["label_score"] > 0]
        group_profiles = [item for item in profiles if not item["is_numeric"] and not item["is_datetime"] and item["group_score"] > 0]

        if time_profiles:
            time_profile = sorted(time_profiles, key=lambda item: (item["row_coverage"], item["unique_count"]), reverse=True)[0]
            line_metrics = _select_line_metrics(metric_profiles)
            if line_metrics:
                filtered = chart_df[[time_profile["name"]] + line_metrics].dropna(subset=[time_profile["name"]])
                if len(filtered) >= 2:
                    return {
                        "type": "line",
                        "data": filtered.sort_values(time_profile["name"]),
                        "x": time_profile["name"],
                        "y": line_metrics,
                    }

        best_metric = _best_metric(metric_profiles)
        if best_metric is None:
            return None

        label_profile = _select_label_column(label_profiles)
        if label_profile is not None:
            color_profile = _select_color_column(group_profiles, label_profile["name"])
            plot_columns = [label_profile["name"], best_metric["name"]]
            if color_profile is not None:
                plot_columns.append(color_profile["name"])
            plot_columns.extend(_hover_columns(chart_df, excluded_columns=plot_columns))
            dedup_columns = list(dict.fromkeys(plot_columns))
            ranking_df = chart_df[dedup_columns].dropna(subset=[label_profile["name"], best_metric["name"]])
            ranking_df = ranking_df.sort_values(best_metric["name"], ascending=False).head(12).sort_values(best_metric["name"], ascending=True)
            if len(ranking_df) >= 2:
                return {
                    "type": "bar",
                    "data": ranking_df,
                    "x": best_metric["name"],
                    "y": label_profile["name"],
                    "color": color_profile["name"] if color_profile is not None else None,
                    "hover_data": _hover_columns(ranking_df, excluded_columns=[best_metric["name"], label_profile["name"]]),
                }

        non_support_metrics = [item for item in metric_profiles if not item["is_support_metric"]]
        if len(non_support_metrics) >= 2:
            non_support_metrics = sorted(non_support_metrics, key=lambda item: (item["is_priority_metric"], item["metric_score"]), reverse=True)
            x_metric = non_support_metrics[0]["name"]
            comparable = None
            for candidate in non_support_metrics[1:]:
                if _metric_unit(candidate["name"]) == _metric_unit(x_metric):
                    comparable = candidate["name"]
                    break
            if comparable is None:
                comparable = non_support_metrics[1]["name"]
            scatter_df = chart_df[[x_metric, comparable]].dropna()
            if len(scatter_df) >= 3:
                return {
                    "type": "scatter",
                    "data": scatter_df,
                    "x": x_metric,
                    "y": comparable,
                }

        return None

    chart_df = _normalize_chart_df(df)
    spec = _build_chart_spec(chart_df)
    if spec is None:
        return None

    if spec["type"] == "line":
        fig = px.line(spec["data"], x=spec["x"], y=spec["y"], template="plotly_white")
        fig.update_traces(mode='lines+markers', marker=dict(size=6))
    elif spec["type"] == "bar":
        fig = px.bar(
            spec["data"],
            x=spec["x"],
            y=spec["y"],
            color=spec.get("color"),
            orientation="h",
            template="plotly_white",
            hover_data=spec.get("hover_data"),
        )
    elif spec["type"] == "scatter":
        fig = px.scatter(spec["data"], x=spec["x"], y=spec["y"], template="plotly_white")
    else:
        return None

    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), paper_bgcolor="white", plot_bgcolor="white", font_family="IBM Plex Sans", font_color="#1A202C", legend_title_text="")
    fig.update_xaxes(showgrid=True, gridcolor="#E2E8F0", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E2E8F0", zeroline=False)
    return fig

def do_layout(data, placeholder, show_technical=False):
    try:
        message = data.get("message", "")
        has_report_content = any(key in data for key in REPORT_KEYS)

        if "text" in data:
            with placeholder.container():
                st.markdown("<div class='section-card'><div class='section-title'>Richiesta in corso</div></div>", unsafe_allow_html=True)
                st.write(data.get("text", ""))
            return

        if "Feedback" in data:
            return

        if not has_report_content:
            with placeholder.container():
                st.markdown("<div class='section-card'><div class='section-title'>Risposta</div></div>", unsafe_allow_html=True)
                st.write(message)
            return

        parse_result = normalize_report_payload(data)
        report = parse_result.report
        with placeholder.container():
            st.markdown(f"<div class='section-card'><div class='mono-label'>Executive Summary</div><div class='section-title'>{report.report_title}</div></div>", unsafe_allow_html=True)
            if not parse_result.is_valid and show_technical:
                st.warning("Risposta parzialmente non conforme allo schema: applicati fallback automatici.")
                with st.expander("Dettaglio errori schema", expanded=False):
                    st.write(parse_result.errors)
            st.write(report.summary)
            if message:
                st.info(message)

            table_data = report.table_data
            if table_data:
                df = pd.DataFrame(table_data)
                if 'laboratorydata_ptr_id' in df.columns:
                    df.drop('laboratorydata_ptr_id', axis=1, inplace=True)
                st.markdown("<div class='section-card'><div class='section-title'>Dettaglio dati</div></div>", unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True, hide_index=True)
                fig = render_chart(df)
                if fig is not None:
                    st.markdown("<div class='section-card'><div class='section-title'>Visualizzazione</div></div>", unsafe_allow_html=True)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.markdown(
                        "<div class='chart-empty-state'><strong>Visualizzazione non disponibile</strong>Nessun dato numerico disponibile per il grafico.</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Nessun dato tabellare disponibile.")

            st.markdown("<div class='section-card'><div class='section-title'>Conclusioni</div></div>", unsafe_allow_html=True)
            st.write(report.conclusions)

            _render_detailed_report_panel(data)

            if show_technical:
                with st.expander("Strumenti tecnici", expanded=False):
                    with st.expander("Payload JSON", expanded=False):
                        st.json(data)
    except Exception as exc:
        placeholder.empty()
        placeholder.error(f"Errore nel caricamento dei dati: {exc}")
        time.sleep(1)


def render_empty_state():
    st.markdown(
        """
        <div class="hero-box">
            <div class="mono-label">Ceramic surfaces intelligence</div>
            <div class="hero-title">Rational Analytics Workspace</div>
            <div class="hero-copy">
                Una versione demo pensata per mostrare analisi e metriche su produzione, disponibilità e laboratorio in modo chiaro e leggibile                
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    for group_index, (group_name, prompts) in enumerate(QUICK_PROMPT_GROUPS.items()):
        st.markdown(f"<div class='section-card'><div class='mono-label'>{group_name}</div></div>", unsafe_allow_html=True)
        prompt_columns = st.columns(2, gap="small")
        for prompt_index, prompt in enumerate(prompts):
            with prompt_columns[prompt_index % 2]:
                if st.button(prompt, key=f"quick_prompt_demo2_{group_index}_{prompt_index}", use_container_width=True, disabled=st.session_state.request_in_flight):
                    st.session_state.prefilled_request = prompt
                    st.session_state.input_counter += 1
                    st.rerun()


def main():
    inject_demo_styles()

    if 'conversation' not in st.session_state:
        st.session_state.conversation = []
    if 'selected_response' not in st.session_state:
        st.session_state.selected_response = None
    if 'assistant_thread_id' not in st.session_state:
        st.session_state.assistant_thread_id = f"conv_{uuid4()}"
        log_conversation_event(st.session_state.assistant_thread_id, "conversation_started", payload={"source": "demo2Chat_session_init"})
    if 'input_counter' not in st.session_state:
        st.session_state.input_counter = 0
    if 'last_audio_hash' not in st.session_state:
        st.session_state.last_audio_hash = None
    if 'prefilled_request' not in st.session_state:
        st.session_state.prefilled_request = ""
    if 'last_request_processed' not in st.session_state:
        st.session_state.last_request_processed = None
    if 'demo2_show_technical' not in st.session_state:
        st.session_state.demo2_show_technical = False
    if 'request_in_flight' not in st.session_state:
        st.session_state.request_in_flight = False

    with st.sidebar:
        st.markdown("<div class='brand-box'><div class='brand-title'>CERAMIC.AI</div><div class='brand-subtitle'>demo interface</div></div>", unsafe_allow_html=True)
        if st.button("Nuova conversazione", use_container_width=True, type="primary"):
            st.session_state.conversation = []
            st.session_state.selected_response = None
            st.session_state.last_request_processed = None
            st.session_state.prefilled_request = ""
            st.session_state.last_audio_hash = None
            st.session_state.request_in_flight = False
            st.session_state.input_counter += 1
            st.session_state.assistant_thread_id = f"conv_{uuid4()}"
            log_conversation_event(st.session_state.assistant_thread_id, "conversation_started", payload={"source": "demo2Chat_new_conversation_button"})
            st.rerun()
        st.markdown("<div class='mono-label' style='margin-bottom:0.45rem;'>Richieste</div>", unsafe_allow_html=True)
        if st.session_state.conversation:
            for idx, item in enumerate(st.session_state.conversation):
                label = f"[{item['timestamp']}] {item['request']}"
                if st.button(label, key=f"request_demo2_{idx}", use_container_width=True):
                    st.session_state.selected_response = idx
                    st.rerun()
        else:
            st.markdown("<div class='empty-history'>Sistema pronto per nuove richieste su stock, produzione e laboratorio.</div>", unsafe_allow_html=True)
        with st.expander("Pannello tecnico", expanded=False):
            st.session_state.demo2_show_technical = st.checkbox("Mostra dettagli tecnici", value=st.session_state.demo2_show_technical)
            st.caption(f"Conversation ID: {st.session_state.assistant_thread_id}")

        st.markdown("<div class='powered-footer'>", unsafe_allow_html=True)
        if POWERED_LOGO_PATH.exists():
            st.image(str(POWERED_LOGO_PATH), width=170)
        

    st.markdown("<div class='top-status'><span class='status-dot'></span><span>System operational</span></div>", unsafe_allow_html=True)

    control_col1, control_col2, control_col3 = st.columns([1.0, 1.2, 3.6], gap="small")
    with control_col1:
        st.markdown("<div class='mono-label'>Sessione attiva</div>", unsafe_allow_html=True)
    with control_col2:
        audio_input = st.audio_input("Registra richiesta vocale", label_visibility="collapsed")
    with control_col3:
        with st.form(key=f"request_form_{st.session_state.input_counter}", clear_on_submit=False, border=False):
            form_input_col, form_button_col = st.columns([5.2, 1.1], gap="small")
            with form_input_col:
                nuova_richiesta = st.text_input(
                    "Nuova richiesta all'assistente",
                    key=f"input_request_{st.session_state.input_counter}",
                    value=st.session_state.prefilled_request,
                    placeholder="Chiedi un'analisi su ordini, disponibilita, produzione o laboratorio...",
                    label_visibility="collapsed",
                    disabled=st.session_state.request_in_flight,
                )
            with form_button_col:
                submit_requested = st.form_submit_button("Invia", type="primary", use_container_width=True, disabled=st.session_state.request_in_flight)
        if st.session_state.request_in_flight:
            st.caption("Richiesta in elaborazione. Attendi il completamento prima di inviarne un'altra.")

    if audio_input is not None:
        audio_bytes = audio_input.getvalue()
        current_hash = hashlib.sha256(audio_bytes).hexdigest()
        if current_hash != st.session_state.last_audio_hash:
            with st.spinner("Trascrizione vocale in corso..."):
                testo_vocale = transcribe_streamlit_audio(audio_input)
            if testo_vocale:
                st.success("Trascrizione completata")
                st.session_state.prefilled_request = testo_vocale
                st.session_state.last_audio_hash = current_hash
                st.session_state.input_counter += 1
                st.rerun()

    placeholder = st.empty()
    if st.session_state.selected_response is not None:
        if st.session_state.selected_response >= 0:
            selected_item = st.session_state.conversation[st.session_state.selected_response]
            if isinstance(selected_item['response'], str):
                try:
                    data = json.loads(selected_item['response'])
                except Exception:
                    st.warning("Errore nel caricamento della risposta JSON.")
                    data = {}
            else:
                data = selected_item['response']
        else:
            with open("data.json", "r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        do_layout(data, placeholder, show_technical=st.session_state.demo2_show_technical)
    elif not st.session_state.conversation:
        render_empty_state()

    if st.session_state.demo2_show_technical:
        st.divider()
        with st.expander("Log runtime conversazione", expanded=False):
            max_lines = st.number_input("Righe da visualizzare", min_value=20, max_value=1000, value=120, step=20)
            log_path, log_tail = read_conversation_log_tail(st.session_state.assistant_thread_id, int(max_lines))
            if log_path:
                st.caption(str(log_path))
                st.text_area("Log (tail)", value=log_tail, height=260)
            else:
                st.info(log_tail)

    if submit_requested and nuova_richiesta and nuova_richiesta != st.session_state.last_request_processed and not st.session_state.request_in_flight:
        placeholder.write("Elaborazione in corso...")
        st.session_state.request_in_flight = True
        log_conversation_event(st.session_state.assistant_thread_id, "user_input_submitted", payload={"request_text": nuova_richiesta})
        try:
            write_text_to_json(nuova_richiesta)
            handle_request(nuova_richiesta, thread_id=st.session_state.assistant_thread_id)
            data = json.load(open("data.json", "r", encoding="utf-8"))
        except Exception:
            st.session_state.request_in_flight = False
            raise
        st.session_state.request_in_flight = False
        st.session_state.last_request_processed = nuova_richiesta
        st.session_state.prefilled_request = ""
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.conversation.append({'request': nuova_richiesta, 'response': data, 'timestamp': timestamp})
        st.session_state.selected_response = -1
        st.session_state.input_counter += 1
        st.rerun()


if __name__ == "__main__":
    main()
