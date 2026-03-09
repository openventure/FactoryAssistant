import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

GAMMA_API_BASE = "https://public-api.gamma.app/v1.0"
GAMMA_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "gamma_requests.log"


class GammaAPIError(RuntimeError):
    pass


def _safe_json_dumps(payload):
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


def _clip_text(text, max_chars=1200):
    raw = text if isinstance(text, str) else _safe_json_dumps(text)
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "... [truncated]"


def _log_gamma_event(event, payload=None):
    GAMMA_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    payload_text = _safe_json_dumps(payload or {})
    with open(GAMMA_LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] event={event} payload={payload_text}\n")


def _require_api_key(api_key=None):
    resolved_key = (api_key or os.getenv("GAMMA_API_KEY", "")).strip()
    if not resolved_key:
        raise GammaAPIError("GAMMA_API_KEY non configurata.")
    return resolved_key


def _require_template_id(template_id=None):
    resolved_template = (template_id or os.getenv("GAMMA_TEMPLATE_ID", "")).strip()
    if not resolved_template:
        raise GammaAPIError("GAMMA_TEMPLATE_ID non configurato.")
    return resolved_template


def _parse_folder_ids(folder_ids=None):
    if folder_ids is not None:
        return folder_ids
    raw = os.getenv("GAMMA_FOLDER_IDS", "").strip()
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_prompt_from_report(report_payload, max_rows=250):
    payload_for_gamma = dict(report_payload or {})
    table_data = payload_for_gamma.get("table_data")
    if isinstance(table_data, list) and len(table_data) > max_rows:
        payload_for_gamma["table_data"] = table_data[:max_rows]
        payload_for_gamma["note"] = (
            f"{payload_for_gamma.get('note', '')}\n"
            f"Dataset troncato automaticamente a {max_rows} righe per il rendering Gamma."
        ).strip()

    json_payload = json.dumps(payload_for_gamma, ensure_ascii=False, indent=2, default=str)
    return (
        "Crea una pagina con grafica professionale in italiano.\n"
        "Metti in evidenza KPI, insight chiave, trend e conclusioni operative.\n"
        "Usa il JSON seguente come sorgente dati principale:\n\n"
        f"{json_payload}"
    )


def create_generation_from_template(report_payload, api_key=None, template_id=None, timeout_sec=40):
    key = _require_api_key(api_key)
    gamma_template_id = _require_template_id(template_id)
    endpoint = f"{GAMMA_API_BASE}/generations/from-template"

    body = {
        "prompt": build_prompt_from_report(report_payload),
        "gammaId": gamma_template_id,
    }

    theme_id = os.getenv("GAMMA_THEME_ID", "").strip()
    if theme_id:
        body["themeId"] = theme_id

    folder_ids = _parse_folder_ids()
    if folder_ids:
        body["folderIds"] = folder_ids

    export_as = os.getenv("GAMMA_EXPORT_AS", "").strip()
    if export_as:
        body["exportAs"] = export_as

    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "X-API-KEY": key,
    }

    _log_gamma_event(
        "create_request",
        {
            "endpoint": endpoint,
            "template_id": gamma_template_id,
            "prompt_chars": len(body.get("prompt", "")),
            "prompt_preview": _clip_text(body.get("prompt", "")),
            "theme_id": body.get("themeId"),
            "folder_ids": body.get("folderIds"),
            "export_as": body.get("exportAs"),
            "timeout_sec": timeout_sec,
        },
    )

    response = requests.post(endpoint, headers=headers, json=body, timeout=timeout_sec)
    _log_gamma_event(
        "create_response",
        {
            "status_code": response.status_code,
            "ok": response.ok,
            "body_preview": _clip_text(response.text),
        },
    )
    if not response.ok:
        raise GammaAPIError(f"Errore Gamma create: HTTP {response.status_code} - {response.text}")

    payload = response.json()
    generation_id = payload.get("generationId") or payload.get("id")
    if not generation_id:
        raise GammaAPIError(f"Risposta Gamma inattesa (manca generationId): {payload}")

    _log_gamma_event(
        "create_parsed",
        {
            "generation_id": generation_id,
            "payload": payload,
        },
    )

    return {"generation_id": generation_id, "raw": payload}


def get_generation_status(generation_id, api_key=None, timeout_sec=25):
    key = _require_api_key(api_key)
    endpoint = f"{GAMMA_API_BASE}/generations/{generation_id}"
    headers = {"accept": "application/json", "X-API-KEY": key}

    _log_gamma_event(
        "status_request",
        {
            "endpoint": endpoint,
            "generation_id": generation_id,
            "timeout_sec": timeout_sec,
        },
    )

    response = requests.get(endpoint, headers=headers, timeout=timeout_sec)
    _log_gamma_event(
        "status_response",
        {
            "generation_id": generation_id,
            "status_code": response.status_code,
            "ok": response.ok,
            "body_preview": _clip_text(response.text),
        },
    )
    if not response.ok:
        raise GammaAPIError(f"Errore Gamma status: HTTP {response.status_code} - {response.text}")

    payload = response.json()
    status = str(payload.get("status", "unknown")).lower()
    gamma_url = payload.get("gammaUrl") or payload.get("url")
    output_file_url = payload.get("outputFileUrl")

    _log_gamma_event(
        "status_parsed",
        {
            "generation_id": generation_id,
            "status": status,
            "gamma_url": gamma_url,
            "output_file_url": output_file_url,
        },
    )

    return {
        "generation_id": generation_id,
        "status": status,
        "gamma_url": gamma_url,
        "output_file_url": output_file_url,
        "raw": payload,
    }


def wait_for_generation(generation_id, api_key=None, timeout_sec=180, poll_seconds=4):
    deadline = time.time() + timeout_sec
    last_status = None

    _log_gamma_event(
        "wait_started",
        {
            "generation_id": generation_id,
            "timeout_sec": timeout_sec,
            "poll_seconds": poll_seconds,
        },
    )

    while time.time() < deadline:
        current = get_generation_status(generation_id, api_key=api_key)
        status = current.get("status", "unknown")
        last_status = current
        _log_gamma_event(
            "wait_poll",
            {
                "generation_id": generation_id,
                "status": status,
            },
        )
        if status in {"completed", "succeeded", "ready", "done"}:
            current["timed_out"] = False
            _log_gamma_event(
                "wait_completed",
                {
                    "generation_id": generation_id,
                    "status": status,
                },
            )
            return current
        if status in {"failed", "error", "cancelled"}:
            _log_gamma_event(
                "wait_failed",
                {
                    "generation_id": generation_id,
                    "status": status,
                    "raw": current.get("raw"),
                },
            )
            raise GammaAPIError(f"Generazione Gamma fallita: {current.get('raw')}")
        time.sleep(poll_seconds)

    if last_status is None:
        last_status = {"generation_id": generation_id, "status": "unknown", "raw": {}}
    last_status["timed_out"] = True
    _log_gamma_event(
        "wait_timed_out",
        {
            "generation_id": generation_id,
            "last_status": last_status.get("status"),
        },
    )
    return last_status


def start_generation_and_wait(report_payload, api_key=None, template_id=None, timeout_sec=180, poll_seconds=4):
    _log_gamma_event(
        "start_generation_and_wait_called",
        {
            "timeout_sec": timeout_sec,
            "poll_seconds": poll_seconds,
            "report_keys": sorted(list((report_payload or {}).keys())),
            "table_rows": len((report_payload or {}).get("table_data", []) or []),
        },
    )

    creation = create_generation_from_template(
        report_payload=report_payload,
        api_key=api_key,
        template_id=template_id,
    )
    generation_id = creation["generation_id"]
    status_payload = wait_for_generation(
        generation_id=generation_id,
        api_key=api_key,
        timeout_sec=timeout_sec,
        poll_seconds=poll_seconds,
    )
    status_payload["creation"] = creation["raw"]

    _log_gamma_event(
        "start_generation_and_wait_completed",
        {
            "generation_id": generation_id,
            "status": status_payload.get("status"),
            "timed_out": status_payload.get("timed_out"),
        },
    )
    return status_payload
