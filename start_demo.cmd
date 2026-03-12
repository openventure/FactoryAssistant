cd \projects\openventure\FactoryAssistance
call env\Scripts\activate
set PYTHONPATH=%CD%
SET DEBUG_MODE=False
Set PYDEVD_DISABLE_FILE_VALIDATION=1
SET SQLITE_PATH=C:\projects\openventure\EasyCert\EasyCertWebProject\db_produzione.sqlite3
SET GAMMA_TEMPLATE_ID=g_gt47bfh3moq4gnt
SET GAMMA_THEME_ID=0wz4q3p8x1cvw00

env\Scripts\python.exe assistente_produzione\run_streamlit.py
