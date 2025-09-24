import openai
import os

# Recupera la chiave API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Recupera la lista degli assistenti
assistants = openai.beta.assistants.list()

# Mostra gli ID e i nomi degli assistenti
for assistant in assistants.data:
    print(f"ID: {assistant.id} - Nome: {assistant.name}")
