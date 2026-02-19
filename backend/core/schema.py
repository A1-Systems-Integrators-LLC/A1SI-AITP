"""OpenAPI schema customization for drf-spectacular."""


def auto_tag_endpoints(endpoints, **kwargs):
    """Preprocessing hook that assigns tags based on URL path prefix.

    Maps /api/<prefix>/... to a human-readable tag name, giving
    Swagger UI clean grouping without per-view @extend_schema decorators.
    """
    tag_map = {
        "/api/auth/": "Auth",
        "/api/health": "Platform",
        "/api/platform/": "Platform",
        "/api/notifications/": "Platform",
        "/api/portfolios/": "Portfolio",
        "/api/trading/": "Trading",
        "/api/live-trading/": "Trading",
        "/api/paper-trading/": "Trading",
        "/api/exchange-configs/": "Market",
        "/api/data-sources/": "Market",
        "/api/exchanges/": "Market",
        "/api/market/": "Market",
        "/api/indicators/": "Market",
        "/api/regime/": "Regime",
        "/api/risk/": "Risk",
        "/api/jobs/": "Analysis",
        "/api/backtest/": "Analysis",
        "/api/screening/": "Analysis",
        "/api/data/": "Analysis",
        "/api/ml/": "ML",
        "/metrics/": "Platform",
    }

    for path, _path_regex, _method, callback in endpoints:
        # Find matching tag
        for prefix, tag in tag_map.items():
            if path.startswith(prefix):
                if hasattr(callback, "cls"):
                    # Set tag via initkwargs so spectacular picks it up
                    if not hasattr(callback, "initkwargs"):
                        callback.initkwargs = {}
                    callback.initkwargs.setdefault("tags", [tag])
                break

    return endpoints
