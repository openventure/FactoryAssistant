import os
import sys
from streamlit.web import cli as stcli


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    sys.path.insert(0, project_root)
    os.environ.setdefault("DEBUG_MODE", "True")
    sys.argv = [
        "streamlit",
        "run",
        "modules/visualization/testChat.py",
        "--server.fileWatcherType",
        "none",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
