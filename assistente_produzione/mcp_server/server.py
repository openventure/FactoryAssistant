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
        """Find articles in pa_ff_code by format, code, series, or description."""
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
        article_code: str,
        cod_var: str = "",
        deposit_contains: str = "",
        format_filter: str = "",
        limit: int = 50,
    ) -> dict:
        """Return deposit-level risk rows from dashboard_productavailability for a specific article code."""
        items = get_stock_risk_by_deposit(
            article_code=article_code,
            cod_var=cod_var or None,
            deposit_contains=deposit_contains or None,
            format_filter=format_filter or None,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "dashboard_productavailability",
            "article_code": article_code,
        }

    @mcp.tool()
    def get_production_by_line_tool(
        days: int = 30,
        line_filter: str = "",
        first_choice_only: bool = False,
        include_expelled: bool = False,
        limit: int = 20,
    ) -> dict:
        """Return aggregated production KPIs by line from PALLET_PRODUCTION for the requested period."""
        items = get_production_summary_by_line(
            days=days,
            line_filter=line_filter or None,
            first_choice_only=first_choice_only,
            include_expelled=include_expelled,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "PALLET_PRODUCTION",
            "days": days,
        }

    @mcp.tool()
    def get_article_production_tool(
        days: int = 30,
        article_code: str = "",
        format_filter: str = "",
        line_filter: str = "",
        first_choice_only: bool = False,
        include_expelled: bool = False,
        limit: int = 20,
    ) -> dict:
        """Return top produced articles and volume in square meters from PALLET_PRODUCTION."""
        items = get_article_production(
            days=days,
            article_code=article_code or None,
            format_filter=format_filter or None,
            line_filter=line_filter or None,
            first_choice_only=first_choice_only,
            include_expelled=include_expelled,
            limit=limit,
        )
        return {
            "items": items,
            "count": len(items),
            "source": "PALLET_PRODUCTION",
            "days": days,
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
