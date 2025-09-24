import openai
#todo una tantum!
 
import os

# Recupera la chiave API dalla variabile d'ambiente
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
assistant = openai.beta.assistants.create(
    name="Data Visualization Assistant",
    instructions="""
Il tuo compito è analizzare i dati tabellari forniti nel JSON di input e scegliere il miglior tipo di grafico per rappresentarli in modo efficace. Segui questi passaggi:

1️⃣ **Comprendere la Struttura dei Dati**  
   - Il JSON contiene una richiesta dell'utente, un titolo del report, un riassunto, dati tabellari e conclusioni.  
   - I dati tabellari si trovano in `table_data` e sono un array di oggetti con diverse colonne.  
   - Identifica le colonne chiave (es. date, valori numerici, categorie).

2️⃣ **Determinare l'Obiettivo della Visualizzazione**  
   - Se la richiesta dell'utente riguarda l'**andamento nel tempo**, scegli un **grafico a linee**.
   - Se il focus è **confrontare categorie**, usa un **grafico a barre**.
   - Se l'obiettivo è **analizzare distribuzioni**, un **box plot** è più adatto.
   - Se bisogna evidenziare **correlazioni**, considera uno **scatter plot** o una **heatmap**.

3️⃣ **Applicare la Logica di Scelta del Grafico**  
   - Se esiste una **colonna con date**, scegli un **grafico a linee** per visualizzare il trend temporale.
   - Se ci sono **valori numerici raggruppabili per categoria**, usa un **grafico a barre**.
   - Se i dati contengono **variazioni di un valore per categorie ripetute**, un **box plot** è ideale.
   - Se sono presenti **due variabili numeriche correlate**, usa uno **scatter plot**.
   - Se hai dati di categoria con valori numerici in più gruppi, considera una **heatmap**.

4️⃣ **Generare il JSON di Output**  
   - Il formato JSON di output deve essere **identico** all'input, con le seguenti modifiche:
     - `"table_data"` deve essere aggiornato con eventuali considerazioni (ad es. aggiungere aggregazioni o filtri se necessari).
     - Aggiungere la chiave `"graphic_type"`, che contiene una stringa con il tipo di grafico scelto.
   - **Esempio di output corretto:**  

   ```json
   {
       "user_request": "Domanda originale dell'utente",
       "report_title": "Titolo del report",
       "summary": "Descrizione sommaria dei dati analizzati",
       "table_data": [{ "colonna1": "valore1_modificato", "colonna2": "valore2_modificato" }],
       "conclusions": "Considerazioni finali basate sui dati",
       "graphic_type": "line_chart"
   }""",
        model="gpt-4o",
        tools=[]
 )
assistant_id = assistant.id
print("Assistant ID:", assistant_id)





