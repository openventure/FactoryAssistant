import os
import sys
from streamlit.web import cli as stcli

def main():
    # Assicura root progetto nel path (utile per i tuoi import assoluti)
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    # Se vuoi evitare di settare env da VS
    os.environ.setdefault("DEBUG_MODE", "True")

    # Lancia Streamlit come se fosse: streamlit run <file> --server.fileWatcherType none
    sys.argv = [
        "streamlit",
        "run",
        "modules/visualization/initChat.py",
        "--server.fileWatcherType",
        "none",
    ]
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()
