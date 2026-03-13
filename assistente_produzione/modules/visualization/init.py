from itertools import count
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
import debugpy
import os


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

DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

if DEBUG_MODE:
    import debugpy
    debugpy.listen(("localhost", 5678))
    print("🔍 Debugger in attesa di connessione....")
    debugpy.wait_for_client()
    print("✅ Debugger connesso, avvio Streamlit!")


st.title("📊 Dashboard Dinamica")
last_data = None  # Per confrontare i cambiamenti nel file JSON
json_path = "data.json"
graphic_displayed = False
after_done = False  # Flag per riconoscere il messaggio successivo a "Done"

# Placeholder per aggiornare i dati
placeholder = st.empty()
placeholder_transcr = st.empty()

while True:
    try:
        # 🔹 1. Legge i dati da "data.json"
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        message = data.get("message", "")

        if data == last_data:
            time.sleep(5)
            continue  # Se i dati sono uguali, non aggiorna la dashboard
        placeholder.empty()
        last_data = data  # Aggiorna il valore di confronto

        if "text" in data:
            text = data.get("text", "")
            with placeholder_transcr:
                    st.write(text)
            data = {"Feedback": "True"}
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        elif "Feedback" not in data:
            if "message" not in data:
                graphic_displayed = True
                after_done = True  # Attiviamo la flag per il messaggio successivo

                # 🔹 2. Estrai le sezioni principali del JSON
                user_request = data.get("user_request", "Richiesta non disponibile")
                report_title = data.get("report_title", "Titolo non disponibile")
                summary = data.get("summary", "Nessun riassunto disponibile")
                table_data = data.get("table_data", [])
                conclusions = data.get("conclusions", "Nessuna conclusione disponibile")

                # 🔹 3. Visualizza il report
                with placeholder.container():
                    
                    st.write("⌨️ Premi Ctrl+I per avviare la registrazione...")
                    st.subheader(f"📌 {report_title}")
                    st.write(f"🔎 **Analisi:** {summary}")

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
                    st.write(conclusions)
            else:
                # 🔹 Normalmente, svuotiamo la dashboard e mostriamo i messaggi
                with placeholder:
                    st.write(message)
            time.sleep(5)

    except Exception as e:
        placeholder.empty()
        placeholder.error(f"❌ Errore nel caricamento dei dati: {e}")
        time.sleep(5)
