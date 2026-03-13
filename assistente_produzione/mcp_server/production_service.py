from __future__ import annotations

from typing import Any

from sqlalchemy import text

from assistente_produzione.modules.request_processing.MaketheQuery import engine_sqlserver2

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_DAYS = 30
MAX_DAYS = 365


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


def get_production_summary_by_line(
    days: int | None = None,
    line_filter: str | None = None,
    first_choice_only: bool = False,
    include_expelled: bool = False,
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
      AND (:include_expelled = 1 OR p.Espulso = 0 OR p.Espulso IS NULL)
      AND (:first_choice_only = 0 OR p.LGV_numeroScelta = 'I')
    GROUP BY p.Linea, period.start_date, period.end_date
    ORDER BY total_m2 DESC, total_pallets DESC, p.Linea ASC
    """
    params = {
        "days": safe_days,
        "line_filter": _like_or_none(line_filter),
        "include_expelled": 1 if include_expelled else 0,
        "first_choice_only": 1 if first_choice_only else 0,
    }
    with engine_sqlserver2.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def get_article_production(
    days: int | None = None,
    article_code: str | None = None,
    format_filter: str | None = None,
    line_filter: str | None = None,
    first_choice_only: bool = False,
    include_expelled: bool = False,
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
      AND (:include_expelled = 1 OR p.Espulso = 0 OR p.Espulso IS NULL)
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
        "include_expelled": 1 if include_expelled else 0,
        "first_choice_only": 1 if first_choice_only else 0,
    }
    with engine_sqlserver2.connect() as connection:
        rows = connection.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]
