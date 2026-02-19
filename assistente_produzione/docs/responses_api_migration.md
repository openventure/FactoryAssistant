# Migrazione da Assistants API (beta) a Responses API

## Stato attuale nell'app

L'app usa ancora il flusso Assistants API con:

- `openai.beta.assistants.retrieve(...)`
- `openai.beta.threads.create(...)`
- `openai.beta.threads.messages.create(...)`
- `openai.beta.threads.runs.create(...)`
- `openai.beta.threads.runs.submit_tool_outputs(...)`

Questo è visibile in `modules/request_processing/AssistantLib.py` e `modules/visualization/initChat.py`.

## Conviene passare a Responses API?

Sì, conviene pianificare la migrazione.

Motivi principali:

1. **Allineamento con API più moderna**: Responses API unifica meglio output, tool e orchestrazione.
2. **Meno dipendenza da `threads/runs` legacy**: riduce il lock-in su pattern che possono cambiare.
3. **Flusso più diretto**: un ciclo richiesta/risposta e tool call più semplice da governare lato applicazione.

## Come portare il "contesto assistente"

Il contesto oggi è principalmente nel campo `instructions` dell'assistente creato in `Creazione_assistente.py`.

Con Responses API lo stesso contenuto può essere messo in:

- campo `instructions` della request;
- oppure come messaggio `system` nel blocco `input`;
- e, per conoscenza grande/stabile, su file/vector store interrogato via tool (`file_search`), evitando prompt enormi.

In pratica: il contesto non si perde, si **riorganizza** tra istruzioni di sistema + memoria conversazionale + knowledge esterna.

## Dimensione del contesto: oggi vs nuova implementazione

### Oggi (codice attuale)

Nel codice applicativo è presente un limite esplicito solo sul payload dei risultati tool SQL:

- `max_tokens = 10000` prima dell'invio output tool.

Quindi oggi la parte "risultati query" viene troncata a ~10k token (stima locale con `tiktoken`).

Per il resto (instructions + storia thread) non c'è nel codice un limite applicativo esplicito: il limite effettivo dipende dal modello configurato lato OpenAI.

### Con Responses API

- Anche qui il limite reale dipende dal modello scelto.
- La best practice è: prompt base più snello, storico recente essenziale, e knowledge su file/vector store.
- Se serve un tetto applicativo, mantenere un controllo come l'attuale (`count_tokens`) anche nel nuovo flusso.

## Strategia consigliata di migrazione

1. **Introdurre un adapter**: nuova funzione `handle_request_responses(...)` parallela alla vecchia.
2. **Portare tools**: riuso dello schema funzione `execute_sql_query` con tool calling della Responses API.
3. **Portare contesto**: spostare il testo lungo di `instructions` in system prompt + eventuale knowledge esterna.
4. **Misurare token**: loggare token input/output per confrontare costi e qualità.
5. **Switch graduale**: feature flag per passare da Assistants a Responses senza bloccare produzione.

## Nota pratica

Se vuoi una migrazione "full Responses API", il passaggio migliore è eliminare progressivamente la dipendenza da `openai.beta.threads.*` e mantenere thread/memoria lato app, inviando a ogni chiamata solo il contesto strettamente necessario.


## Scelta demo attuale

In questa demo iniziale il contesto viene passato direttamente come `instructions` caricando `knowledge/production_assistant_knowledge.md`, senza usare vector store.
