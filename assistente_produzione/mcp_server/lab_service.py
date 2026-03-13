from __future__ import annotations

import datetime
import json
from math import sqrt
from pathlib import Path
from typing import Any

from sqlalchemy import text

from assistente_produzione.modules.request_processing.MaketheQuery import engine_sqlite

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_DAYS = 90
MAX_DAYS = 730
DEFAULT_MONTHS = 24
MAX_MONTHS = 36
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


def _normalize_months(months: int | None) -> int:
    if months is None:
        return DEFAULT_MONTHS
    safe_months = int(months)
    if safe_months < 1:
        return DEFAULT_MONTHS
    return min(safe_months, MAX_MONTHS)


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
    with engine_sqlite.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]

def get_absorption_stats_by_article(
    days: int | None = None,
    article_code: str | None = None,
    description_contains: str | None = None,
    tone: str | None = None,
    min_samples: int = 1,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    safe_days = _normalize_days(days)
    safe_limit = _normalize_limit(limit)
    safe_min_samples = max(int(min_samples or 1), 1)
    sql = f"""
    SELECT
        l.CodeArt,
        l.Description,
        COUNT(*) AS n_prove,
        ROUND(AVG(a.Assorbimento), 4) AS Avg_Assorbimento,
        ROUND(MIN(a.Assorbimento), 4) AS Min_Assorbimento,
        ROUND(MAX(a.Assorbimento), 4) AS Max_Assorbimento,
        ROUND(AVG(a.Assorbimento * a.Assorbimento), 6) AS Avg_Assorbimento_Squared,
        MIN(date(l.InsertDate)) AS first_test_date,
        MAX(date(l.InsertDate)) AS last_test_date
    FROM app_laboratorydata l
    JOIN app_assorbimento a ON l.id = a.laboratorydata_ptr_id
    WHERE a.Assorbimento IS NOT NULL
      AND date(l.InsertDate) >= date('now', :days_window)
      AND (:article_code IS NULL OR UPPER(l.CodeArt) = :article_code)
      AND (:description_contains IS NULL OR UPPER(l.Description) LIKE :description_contains)
      AND (:tone IS NULL OR UPPER(l.Tono) LIKE :tone)
    GROUP BY l.CodeArt, l.Description
    HAVING COUNT(*) >= :min_samples
    ORDER BY Avg_Assorbimento DESC, n_prove DESC, l.CodeArt ASC
    LIMIT {safe_limit}
    """
    params = {
        "days_window": f"-{safe_days - 1} days",
        "article_code": article_code.strip().upper() if article_code else None,
        "description_contains": _like_or_none(description_contains),
        "tone": _like_or_none(tone),
        "min_samples": safe_min_samples,
    }
    rows = _execute_logged_query("get_absorption_stats_by_article", sql, params)

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        avg_squared = float(item.pop("Avg_Assorbimento_Squared") or 0)
        mean_value = float(item.get("Avg_Assorbimento") or 0)
        variance = max(avg_squared - (mean_value * mean_value), 0.0)
        item["Std_Assorbimento"] = round(sqrt(variance), 4)
        items.append(item)
    return items


def get_absorption_trend(
    months: int | None = None,
    article_code: str | None = None,
    description_contains: str | None = None,
) -> list[dict[str, Any]]:
    safe_months = _normalize_months(months)
    sql = """
    WITH RECURSIVE months(month_start) AS (
        SELECT date('now', 'start of month', :months_window)
        UNION ALL
        SELECT date(month_start, '+1 month')
        FROM months
        WHERE month_start < date('now', 'start of month')
    ),
    trend AS (
        SELECT
            date(l.InsertDate, 'start of month') AS month_start,
            COUNT(*) AS n_prove,
            ROUND(AVG(a.Assorbimento), 4) AS Avg_Assorbimento
        FROM app_laboratorydata l
        JOIN app_assorbimento a ON l.id = a.laboratorydata_ptr_id
        WHERE a.Assorbimento IS NOT NULL
          AND date(l.InsertDate) >= date('now', 'start of month', :months_window)
          AND (:article_code IS NULL OR UPPER(l.CodeArt) = :article_code)
          AND (:description_contains IS NULL OR UPPER(l.Description) LIKE :description_contains)
        GROUP BY date(l.InsertDate, 'start of month')
    )
    SELECT
        strftime('%Y-%m', months.month_start) AS year_month,
        COALESCE(trend.n_prove, 0) AS n_prove,
        trend.Avg_Assorbimento
    FROM months
    LEFT JOIN trend ON trend.month_start = months.month_start
    ORDER BY months.month_start ASC
    """
    params = {
        "months_window": f"-{safe_months - 1} months",
        "article_code": article_code.strip().upper() if article_code else None,
        "description_contains": _like_or_none(description_contains),
    }
    return _execute_logged_query("get_absorption_trend", sql, params)
