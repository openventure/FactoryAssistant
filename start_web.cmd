cd \projects\openventure\FactoryAssistance
call env\Scripts\activate
set PYTHONPATH=%CD%
SET DEBUG_MODE=False
Set PYDEVD_DISABLE_FILE_VALIDATION=1

env\Scripts\python.exe -m streamlit run assistente_produzione/modules/visualization/initChat.py
