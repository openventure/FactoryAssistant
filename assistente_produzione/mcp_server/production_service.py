from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from assistente_produzione.modules.request_processing.MaketheQuery import engine_sqlserver2

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_DAYS = 30
MAX_DAYS = 365
MCP_SQL_LOG_FILE = Path(__file__).resolve().parents[1] / "logs" / "mcp_sql_queries.log"


def _normalize_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    safe_limit = int(limit)
    if safe_limit < 1:
        return DEFAULT_LIMIT
    return min(safe_limit, MAX_LIMIT)


def _normalize_days(days: int | None) -> int:
    if days is None:
        return DEFAULT_DAYS
    safe_days = int(days)
    if safe_days < 1:
        return DEFAULT_DAYS
    return min(safe_days, MAX_DAYS)


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
    with engine_sqlserver2.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]

def get_production_summary_by_line(
    days: int | None = None,
    line_filter: str | None = None,
    first_choice_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    safe_days = _normalize_days(days)
    safe_limit = _normalize_limit(limit)
    sql = f"""
    WITH period AS (
        SELECT
            CAST(DATEADD(day, -(:days - 1), CAST(GETDATE() AS date)) AS date) AS start_date,
            CAST(GETDATE() AS date) AS end_date
    )
    SELECT TOP {safe_limit}
        p.Linea,
        CAST(SUM(CAST(p.CALC_MQ AS DECIMAL(18,3))) AS DECIMAL(18,3)) AS total_m2,
        COUNT(*) AS total_pallets,
        SUM(COALESCE(p.N_PZ, 0)) AS total_pieces,
        COUNT(DISTINCT CAST(p.START_DATETIME AS date)) AS production_days,
        DATEDIFF(day, period.start_date, period.end_date) + 1 AS calendar_days,
        CAST(
            SUM(CAST(p.CALC_MQ AS DECIMAL(18,3))) /
            NULLIF(DATEDIFF(day, period.start_date, period.end_date) + 1, 0)
            AS DECIMAL(18,3)
        ) AS avg_m2_per_calendar_day,
        CAST(
            SUM(CAST(p.CALC_MQ AS DECIMAL(18,3))) /
            NULLIF(COUNT(DISTINCT CAST(p.START_DATETIME AS date)), 0)
            AS DECIMAL(18,3)
        ) AS avg_m2_per_production_day,
        CAST(
            SUM(CAST(p.CALC_MQ AS DECIMAL(18,3))) /
            NULLIF(COUNT(*), 0)
            AS DECIMAL(18,3)
        ) AS avg_m2_per_pallet,
        SUM(CASE WHEN p.LGV_numeroScelta = 'I' THEN 1 ELSE 0 END) AS first_choice_pallets,
        MIN(CAST(p.START_DATETIME AS date)) AS first_production_date,
        MAX(CAST(p.START_DATETIME AS date)) AS last_production_date
    FROM dbo.PALLET_PRODUCTION p
    CROSS JOIN period
    WHERE p.START_DATETIME >= period.start_date
      AND p.START_DATETIME < DATEADD(day, 1, period.end_date)
      AND (:line_filter IS NULL OR UPPER(p.Linea) LIKE :line_filter)
      AND (:first_choice_only = 0 OR p.LGV_numeroScelta = 'I')
    GROUP BY p.Linea, period.start_date, period.end_date
    ORDER BY total_m2 DESC, total_pallets DESC, p.Linea ASC
    """
    params = {
        "days": safe_days,
        "line_filter": _like_or_none(line_filter),
        "first_choice_only": 1 if first_choice_only else 0,
    }
    return _execute_logged_query("get_production_summary_by_line", sql, params)


def get_article_production(
    days: int | None = None,
    article_code: str | None = None,
    format_filter: str | None = None,
    line_filter: str | None = None,
    first_choice_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    safe_days = _normalize_days(days)
    safe_limit = _normalize_limit(limit)
    sql = f"""
    WITH period AS (
        SELECT
            CAST(DATEADD(day, -(:days - 1), CAST(GETDATE() AS date)) AS date) AS start_date,
            CAST(GETDATE() AS date) AS end_date
    )
    SELECT TOP {safe_limit}
        p.LGV_CodiceArticolo AS article_code,
        CAST(p.FORMATO_LARG AS DECIMAL(18,2)) AS formato_larg,
        CAST(p.FORMATO_LUNG AS DECIMAL(18,2)) AS formato_lung,
        CAST(p.FORMATO_SPES AS DECIMAL(18,2)) AS formato_spes,
        CONCAT(
            CAST(CAST(p.FORMATO_LARG AS DECIMAL(18,0)) AS VARCHAR(20)),
            'x',
            CAST(CAST(p.FORMATO_LUNG AS DECIMAL(18,0)) AS VARCHAR(20))
        ) AS format_label,
        COUNT(*) AS total_pallets,
        CAST(SUM(CAST(p.CALC_MQ AS DECIMAL(18,3))) AS DECIMAL(18,3)) AS total_m2,
        SUM(COALESCE(p.N_PZ, 0)) AS total_pieces,
        COUNT(DISTINCT p.Linea) AS active_lines,
        COUNT(DISTINCT CAST(p.START_DATETIME AS date)) AS production_days,
        SUM(CASE WHEN p.LGV_numeroScelta = 'I' THEN 1 ELSE 0 END) AS first_choice_pallets,
        MIN(CAST(p.START_DATETIME AS date)) AS first_production_date,
        MAX(CAST(p.START_DATETIME AS date)) AS last_production_date
    FROM dbo.PALLET_PRODUCTION p
    CROSS JOIN period
    WHERE p.START_DATETIME >= period.start_date
      AND p.START_DATETIME < DATEADD(day, 1, period.end_date)
      AND p.LGV_CodiceArticolo IS NOT NULL
      AND (:article_code IS NULL OR UPPER(p.LGV_CodiceArticolo) = :article_code)
      AND (:line_filter IS NULL OR UPPER(p.Linea) LIKE :line_filter)
      AND (
          :format_filter IS NULL OR
          UPPER(
              CONCAT(
                  CAST(CAST(p.FORMATO_LARG AS DECIMAL(18,0)) AS VARCHAR(20)),
                  'x',
                  CAST(CAST(p.FORMATO_LUNG AS DECIMAL(18,0)) AS VARCHAR(20))
              )
          ) LIKE :format_filter
      )
      AND (:first_choice_only = 0 OR p.LGV_numeroScelta = 'I')
    GROUP BY
        p.LGV_CodiceArticolo,
        p.FORMATO_LARG,
        p.FORMATO_LUNG,
        p.FORMATO_SPES
    ORDER BY total_m2 DESC, total_pallets DESC, article_code ASC
    """
    params = {
        "days": safe_days,
        "article_code": article_code.strip().upper() if article_code else None,
        "format_filter": _like_or_none(format_filter),
        "line_filter": _like_or_none(line_filter),
        "first_choice_only": 1 if first_choice_only else 0,
    }
    return _execute_logged_query("get_article_production", sql, params)
