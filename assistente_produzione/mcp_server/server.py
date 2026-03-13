from assistente_produzione.mcp_server.lab_service import (
    get_absorption_stats_by_article,
    get_absorption_trend,
)
from assistente_produzione.mcp_server.production_service import (
    get_article_production,
    get_production_summary_by_line,
)
from assistente_produzione.mcp_server.stock_service import (
    find_articles,
    get_stock_risk_articles,
    get_stock_risk_by_deposit,
    get_stock_summary_by_format,
)
import sys
try:
    from mcp.server import FastMCP
except ImportError as exc:  # pragma: no cover - dipendenza opzionale finche non installata
    FastMCP = None
    _MCP_IMPORT_ERROR = exc
else:
    _MCP_IMPORT_ERROR = None

SERVER_NAME = "factory-assistance"
SERVER_INSTRUCTIONS = (
    "Use high-level business tools to retrieve factory data. Prefer semantic tools over raw SQL. "
    "Tools return structured business data already normalized in square meters where applicable."
)


def build_server():
    if FastMCP is None:
        raise RuntimeError(
            "La libreria 'mcp' non e installata. Installa le dipendenze del server MCP prima di avviarlo."
        ) from _MCP_IMPORT_ERROR

    mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @mcp.tool()
    def find_articles_tool(
        format_filter: str = "",
        article_code: str = "",
        series: str = "",
        description_contains: str = "",
        limit: int = 20,
    ) -> dict:
        """Find article-level stock and availability in pa_ff_code by article, format, series, or description."""
        items = find_articles(
            format_filter=format_filter or None,
            article_code=article_code or None,
            series=series or None,
            description_contains=description_contains or None,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "pa_ff_code",
        }

    @mcp.tool()
    def get_stock_risk_articles_tool(
        format_filter: str = "",
        article_code: str = "",
        series: str = "",
        risk_mode: str = "min_stock",
        compare_field: str = "giacenza",
        limit: int = 50,
    ) -> dict:
        """Return article-level stock risk from pa_ff_code using either minimum stock or orders-vs-availability logic."""
        items = get_stock_risk_articles(
            format_filter=format_filter or None,
            article_code=article_code or None,
            series=series or None,
            risk_mode=risk_mode,
            compare_field=compare_field,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "pa_ff_code",
            "risk_mode": risk_mode,
            "compare_field": compare_field,
        }

    @mcp.tool()
    def get_stock_risk_by_deposit_tool(
        article_code: str = "",
        cod_var: str = "",
        deposit_contains: str = "",
        format_filter: str = "",
        limit: int = 50,
    ) -> dict:
        """Return stock by article, deposit, and tone from dashboard_productavailability."""
        items = get_stock_risk_by_deposit(
            article_code=article_code or None,
            cod_var=cod_var or None,
            deposit_contains=deposit_contains or None,
            format_filter=format_filter or None,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "dashboard_productavailability",
            "article_code": article_code or None,
            "format_filter": format_filter or None,
        }

    @mcp.tool()
    def get_stock_summary_by_format_tool(
        format_filter: str = "",
        series: str = "",
        limit: int = 50,
    ) -> dict:
        """Return aggregated current and 30-day stock by format from pa_ff_code."""
        items = get_stock_summary_by_format(
            format_filter=format_filter or None,
            series=series or None,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "pa_ff_code",
        }

    @mcp.tool()
    def get_production_summary_tool(
        group_by: str = "line",
        days: int = 30,
        article_code: str = "",
        format_filter: str = "",
        line_filter: str = "",
        first_choice_only: bool = False,
        limit: int = 20,
    ) -> dict:
        """Return production KPIs from PALLET_PRODUCTION aggregated either by line or by article."""
        group_key = (group_by or "line").strip().lower()
        if group_key == "line":
            items = get_production_summary_by_line(
                days=days,
                line_filter=line_filter or None,
                first_choice_only=first_choice_only,
                limit=limit,
            )
        elif group_key == "article":
            items = get_article_production(
                days=days,
                article_code=article_code or None,
                format_filter=format_filter or None,
                line_filter=line_filter or None,
                first_choice_only=first_choice_only,
                limit=limit,
            )
        else:
            raise ValueError("group_by non supportato. Valori ammessi: line, article.")
        return {
            "items": items,
            "count": len(items),
            "source": "PALLET_PRODUCTION",
            "days": days,
            "group_by": group_key,
        }

    @mcp.tool()
    def get_lab_absorption_stats_tool(
        days: int = 90,
        article_code: str = "",
        description_contains: str = "",
        tone: str = "",
        min_samples: int = 3,
        limit: int = 20,
    ) -> dict:
        """Return average absorption statistics by article from laboratory data."""
        items = get_absorption_stats_by_article(
            days=days,
            article_code=article_code or None,
            description_contains=description_contains or None,
            tone=tone or None,
            min_samples=min_samples,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "app_laboratorydata + app_assorbimento",
            "days": days,
        }

    @mcp.tool()
    def get_lab_absorption_trend_tool(
        months: int = 24,
        article_code: str = "",
        description_contains: str = "",
    ) -> dict:
        """Return monthly laboratory test counts and average absorption trend."""
        items = get_absorption_trend(
            months=months,
            article_code=article_code or None,
            description_contains=description_contains or None,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "app_laboratorydata + app_assorbimento",
            "months": months,
        }

    return mcp


def main() -> None:
    print("Factory Assistance MCP server started", file=sys.stderr)

    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
