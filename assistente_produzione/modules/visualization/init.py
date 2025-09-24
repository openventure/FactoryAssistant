from itertools import count
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
import debugpy
import os

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
