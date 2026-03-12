import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from assistente_produzione.modules.visualization.demo2Chat import do_layout, inject_demo_styles

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_DIR = ROOT_DIR / "assistente_produzione"
FILE_PATTERNS = ("data.json", "data.json_*", "Predata.json", "data_test.json")


def _iter_payload_files(include_app_dir=True):
    seen = set()
    search_roots = [ROOT_DIR]
    if include_app_dir and APP_DIR.exists():
        search_roots.append(APP_DIR)

    collected = []
    for search_root in search_roots:
        for pattern in FILE_PATTERNS:
            for path in search_root.glob(pattern):
                resolved = path.resolve()
                if not path.is_file() or resolved in seen:
                    continue
                seen.add(resolved)
                collected.append(path)

    return sorted(collected, key=lambda item: (item.stat().st_mtime, item.name), reverse=True)


def _load_payload(path):
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _format_sidebar_label(path):
    area = "root" if path.parent == ROOT_DIR else path.parent.name
    timestamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return f"{path.name} [{area}] - {timestamp}"


def main():
    inject_demo_styles()
    st.session_state.setdefault("testchat_show_technical", False)

    with st.sidebar:
        st.markdown("<div class='brand-box'><div class='brand-title'>CERAMIC.AI</div><div class='brand-subtitle'>test chat replay</div></div>", unsafe_allow_html=True)
        include_app_dir = st.checkbox("Includi cartella assistente_produzione", value=True)
        filter_text = st.text_input("Filtra file", placeholder="data.json_20260309...")
        st.session_state.testchat_show_technical = st.checkbox(
            "Mostra dettagli tecnici",
            value=st.session_state.testchat_show_technical,
        )

        payload_files = _iter_payload_files(include_app_dir=include_app_dir)
        if filter_text:
            lowered = filter_text.strip().lower()
            payload_files = [path for path in payload_files if lowered in path.name.lower()]

        if not payload_files:
            st.markdown("<div class='empty-history'>Nessun file JSON compatibile trovato con i filtri correnti.</div>", unsafe_allow_html=True)
            selected_path = None
        else:
            selected_path = st.radio(
                "File JSON salvati",
                payload_files,
                format_func=_format_sidebar_label,
                label_visibility="collapsed",
            )

    st.markdown("<div class='top-status'><span class='status-dot'></span><span>Replay mode</span></div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='section-card'><div class='mono-label'>Offline test</div><div class='section-title'>Storico JSON renderizzato senza richieste live</div></div>",
        unsafe_allow_html=True,
    )

    if selected_path is None:
        st.info("Seleziona un file JSON dalla sidebar per vedere rendering testo, tabella e chart.")
        return

    meta_col1, meta_col2, meta_col3 = st.columns([1.4, 1.2, 2.6])
    with meta_col1:
        st.markdown("<div class='mono-label'>File selezionato</div>", unsafe_allow_html=True)
        st.write(selected_path.name)
    with meta_col2:
        st.markdown("<div class='mono-label'>Ultima modifica</div>", unsafe_allow_html=True)
        st.write(datetime.fromtimestamp(selected_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
    with meta_col3:
        st.markdown("<div class='mono-label'>Percorso</div>", unsafe_allow_html=True)
        st.code(str(selected_path), language=None)

    try:
        data = _load_payload(selected_path)
    except Exception as exc:
        st.error(f"Errore nel caricamento del file JSON: {exc}")
        return

    placeholder = st.empty()
    do_layout(data, placeholder, show_technical=st.session_state.testchat_show_technical)

    with st.expander("JSON sorgente", expanded=False):
        st.json(data)


if __name__ == "__main__":
    main()
