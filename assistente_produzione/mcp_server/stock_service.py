from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from assistente_produzione.modules.request_processing.MaketheQuery import engine_sqlserver

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MCP_SQL_LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "mcp_sql_queries.log"
_COMPARE_COLUMN_MAP = {
    "giacenza": "GIACENZA",
    "disponibilita": "DISPONIBILITA",
}
_RISK_MODE_MAP = {
    "min_stock": "MIN",
    "orders_vs_availability": "QTA_DA_CONSEGNARE",
}


def _normalize_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    safe_limit = int(limit)
    if safe_limit < 1:
        return DEFAULT_LIMIT
    return min(safe_limit, MAX_LIMIT)


def _like_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    return f"%{cleaned}%"




def _format_sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime.datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, datetime.date):
        return "'" + value.strftime("%Y-%m-%d") + "'"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _render_sql_with_params(sql: str, params: dict[str, Any]) -> str:
    rendered = sql
    for key, value in sorted(params.items(), key=lambda item: len(item[0]), reverse=True):
        rendered = rendered.replace(f":{key}", _format_sql_literal(value))
    return rendered.strip()

def _log_sql_query(tool_name: str, sql: str, params: dict[str, Any]) -> None:
    MCP_SQL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    payload = {
        "tool": tool_name,
        "sql": sql.strip(),
        "rendered_sql": _render_sql_with_params(sql, params),
        "params": params,
    }
    with open(MCP_SQL_LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {json.dumps(payload, ensure_ascii=False)}\n")


def _execute_logged_query(tool_name: str, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    _log_sql_query(tool_name, sql, params)
    with engine_sqlserver.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def find_articles(
    format_filter: str | None = None,
    article_code: str | None = None,
    series: str | None = None,
    description_contains: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    safe_limit = _normalize_limit(limit)
    sql = f"""
    SELECT TOP {safe_limit}
        CODICE,
        DESCRIZIONE,
        SERIE,
        FORMATO,
        CAST(MIN AS DECIMAL(18,2)) AS min_stock_m2,
        CAST(GIACENZA AS DECIMAL(18,2)) AS giacenza_m2,
        CAST(DISPONIBILITA AS DECIMAL(18,2)) AS disponibilita_m2,
        CAST(QTA_DA_CONSEGNARE AS DECIMAL(18,2)) AS qta_da_consegnare_m2
    FROM pa_ff_code
    WHERE (:format_filter IS NULL OR UPPER(FORMATO) LIKE :format_filter)
      AND (:article_code IS NULL OR UPPER(CODICE) = :article_code)
      AND (:series IS NULL OR UPPER(SERIE) LIKE :series)
      AND (:description_contains IS NULL OR UPPER(DESCRIZIONE) LIKE :description_contains)
    ORDER BY CODICE ASC
    """
    params = {
        "format_filter": _like_or_none(format_filter),
        "article_code": article_code.strip().upper() if article_code else None,
        "series": _like_or_none(series),
        "description_contains": _like_or_none(description_contains),
    }
    return _execute_logged_query("find_articles", sql, params)


def get_stock_summary_by_format(
    format_filter: str | None = None,
    series: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    safe_limit = _normalize_limit(limit)
    sql = f"""
    SELECT TOP {safe_limit}
        FORMATO,
        COUNT(*) AS article_count,
        CAST(SUM(COALESCE(GIACENZA, 0)) AS DECIMAL(18,2)) AS giacenza_m2,
        CAST(SUM(COALESCE(DISPONIBILITA, 0)) AS DECIMAL(18,2)) AS disponibilita_m2,
        CAST(SUM(COALESCE(GIACENZA_30, 0)) AS DECIMAL(18,2)) AS giacenza_30_m2,
        CAST(SUM(COALESCE(DISPONIBILITA_30, 0)) AS DECIMAL(18,2)) AS disponibilita_30_m2,
        CAST(SUM(COALESCE(QTA_DA_CONSEGNARE, 0)) AS DECIMAL(18,2)) AS qta_da_consegnare_m2        
    FROM pa_ff_code
    WHERE (:format_filter IS NULL OR UPPER(FORMATO) LIKE :format_filter)
      AND (:series IS NULL OR UPPER(SERIE) LIKE :series)
    GROUP BY FORMATO
    ORDER BY giacenza_m2 DESC, FORMATO ASC
    """
    params = {
        "format_filter": _like_or_none(format_filter),
        "series": _like_or_none(series),
    }
    return _execute_logged_query("get_stock_summary_by_format", sql, params)


def get_stock_risk_articles(
    format_filter: str | None = None,
    article_code: str | None = None,
    series: str | None = None,
    compare_field: str = "giacenza",
    risk_mode: str = "min_stock",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    compare_key = (compare_field or "giacenza").strip().lower()
    if compare_key not in _COMPARE_COLUMN_MAP:
        raise ValueError(
            f"compare_field non supportato: {compare_field}. Valori ammessi: {', '.join(sorted(_COMPARE_COLUMN_MAP))}."
        )

    risk_key = (risk_mode or "min_stock").strip().lower()
    if risk_key not in _RISK_MODE_MAP:
        raise ValueError(
            f"risk_mode non supportato: {risk_mode}. Valori ammessi: {', '.join(sorted(_RISK_MODE_MAP))}."
        )

    compare_column = _COMPARE_COLUMN_MAP[compare_key]
    risk_reference_column = _RISK_MODE_MAP[risk_key]
    safe_limit = _normalize_limit(limit)

    if risk_key == "orders_vs_availability" and compare_key == "disponibilita":
        shortage_expression = (
            "CASE WHEN DISPONIBILITA < 0 THEN ABS(DISPONIBILITA) ELSE 0 END"
        )
        where_expression = "DISPONIBILITA < 0"
    else:
        shortage_expression = (
            f"CASE WHEN {compare_column} < {risk_reference_column} THEN {risk_reference_column} - {compare_column} ELSE 0 END"
        )
        where_expression = f"{risk_reference_column} IS NOT NULL AND {compare_column} IS NOT NULL AND {compare_column} < {risk_reference_column}"

    sql = f"""
    SELECT TOP {safe_limit}
        CODICE,
        DESCRIZIONE,
        SERIE,
        FORMATO,
        CAST(MIN AS DECIMAL(18,2)) AS min_stock_m2,
        CAST(GIACENZA AS DECIMAL(18,2)) AS giacenza_m2,
        CAST(DISPONIBILITA AS DECIMAL(18,2)) AS disponibilita_m2,
        CAST(QTA_DA_CONSEGNARE AS DECIMAL(18,2)) AS qta_da_consegnare_m2,
        CAST(
            {shortage_expression}
            AS DECIMAL(18,2)
        ) AS shortage_m2,
        :compare_key AS compare_field_used,
        :risk_key AS risk_mode_used
    FROM pa_ff_code
    WHERE {where_expression}
      AND (:format_filter IS NULL OR UPPER(FORMATO) LIKE :format_filter)
      AND (:article_code IS NULL OR UPPER(CODICE) = :article_code)
      AND (:series IS NULL OR UPPER(SERIE) LIKE :series)
    ORDER BY shortage_m2 DESC, CODICE ASC
    """
    params = {
        "format_filter": _like_or_none(format_filter),
        "article_code": article_code.strip().upper() if article_code else None,
        "series": _like_or_none(series),
        "compare_key": compare_key,
        "risk_key": risk_key,
    }
    return _execute_logged_query("get_stock_risk_articles", sql, params)


def get_stock_risk_by_deposit(
    article_code: str | None = None,
    cod_var: str | None = None,
    deposit_contains: str | None = None,
    format_filter: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized_article_code = (article_code or "").strip().upper()
    normalized_format_filter = _like_or_none(format_filter)
    if not normalized_article_code and normalized_format_filter is None:
        raise ValueError("Specifica almeno article_code oppure format_filter per il dettaglio giacenze depositi.")

    safe_limit = _normalize_limit(limit)
    sql = f"""
    SELECT TOP {safe_limit}
        CODICE,
        DESCRIZIONE,
        FORMATO,
        SERIE,
        COD_VAR AS TONO,
        DEPOSITO,
        CAST(SUM(COALESCE(GIACENZA, 0)) AS DECIMAL(18,2)) AS giacenza_m2
    FROM dashboard_productavailability
    WHERE GIACENZA IS NOT NULL
      AND (:article_code IS NULL OR UPPER(CODICE) = :article_code)
      AND (:cod_var IS NULL OR UPPER(COD_VAR) = :cod_var)
      AND (:deposit_contains IS NULL OR UPPER(DEPOSITO) LIKE :deposit_contains)
      AND (:format_filter IS NULL OR UPPER(FORMATO) LIKE :format_filter)
    GROUP BY CODICE, DESCRIZIONE, FORMATO, SERIE, COD_VAR, DEPOSITO
    ORDER BY giacenza_m2 DESC, CODICE ASC, DEPOSITO ASC, TONO ASC
    """
    params = {
        "article_code": normalized_article_code or None,
        "cod_var": cod_var.strip().upper() if cod_var else None,
        "deposit_contains": _like_or_none(deposit_contains),
        "format_filter": normalized_format_filter,
    }
    return _execute_logged_query("get_stock_risk_by_deposit", sql, params)
