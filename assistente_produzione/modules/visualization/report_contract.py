from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, ValidationError


class ReportResponse(BaseModel):
    user_request: str = "Richiesta non disponibile"
    report_title: str = "Titolo non disponibile"
    summary: str = "Nessun riassunto disponibile"
    table_data: list[dict[str, Any]] = Field(default_factory=list)
    conclusions: str = "Nessuna conclusione disponibile"
    format: str | None = None


class ParseResult(BaseModel):
    report: ReportResponse
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)


def normalize_report_payload(payload: dict[str, Any]) -> ParseResult:
    """
    Converte il JSON della risposta assistant in un contratto stabile per la UI.
    Se il payload non è conforme, applica fallback con errori espliciti.
    """
    try:
        report = ReportResponse.model_validate(payload)
        return ParseResult(report=report, is_valid=True, errors=[])
    except ValidationError as exc:
        fallback = {
            "user_request": payload.get("user_request", "Richiesta non disponibile"),
            "report_title": payload.get("report_title", "Titolo non disponibile"),
            "summary": payload.get("summary", "Nessun riassunto disponibile"),
            "table_data": payload.get("table_data", []),
            "conclusions": payload.get("conclusions", "Nessuna conclusione disponibile"),
            "format": payload.get("format"),
        }

        # Sanificazione minima dei tipi più frequenti
        if not isinstance(fallback["table_data"], list):
            fallback["table_data"] = []
        if not isinstance(fallback["summary"], str):
            fallback["summary"] = str(fallback["summary"])
        if not isinstance(fallback["conclusions"], str):
            fallback["conclusions"] = str(fallback["conclusions"])

        report = ReportResponse.model_validate(fallback)
        errors = [err["msg"] for err in exc.errors()]
        return ParseResult(report=report, is_valid=False, errors=errors)
