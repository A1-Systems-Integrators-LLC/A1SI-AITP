"""Market views — exchange info, tickers, OHLCV, indicators, regime."""

from concurrent.futures import ThreadPoolExecutor

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indicator")


class ExchangeListView(APIView):
    def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService

        service = ExchangeService()
        return Response(service.list_exchanges())


class TickerView(APIView):
    async def get(self, request: Request, symbol: str) -> Response:
        from market.services.exchange import ExchangeService

        service = ExchangeService()
        try:
            ticker = await service.fetch_ticker(symbol)
            return Response(ticker)
        finally:
            await service.close()


class TickerListView(APIView):
    async def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService

        symbols_param = request.query_params.get("symbols")
        symbol_list = symbols_param.split(",") if symbols_param else None

        service = ExchangeService()
        try:
            tickers = await service.fetch_tickers(symbol_list)
            return Response(tickers)
        finally:
            await service.close()


class OHLCVView(APIView):
    async def get(self, request: Request, symbol: str) -> Response:
        from market.services.exchange import ExchangeService

        timeframe = request.query_params.get("timeframe", "1h")
        limit = int(request.query_params.get("limit", 100))
        limit = max(1, min(limit, 1000))

        service = ExchangeService()
        try:
            data = await service.fetch_ohlcv(symbol, timeframe, limit)
            return Response(data)
        finally:
            await service.close()


class IndicatorListView(APIView):
    def get(self, request: Request) -> Response:
        from market.services.indicators import IndicatorService

        return Response(IndicatorService.list_available())


class IndicatorComputeView(APIView):
    def get(self, request: Request, exchange: str, symbol: str, timeframe: str) -> Response:
        from market.services.indicators import IndicatorService

        real_symbol = symbol.replace("_", "/")
        indicators_param = request.query_params.get("indicators", "")
        ind_list = (
            [i.strip() for i in indicators_param.split(",") if i.strip()]
            if indicators_param
            else None
        )
        limit = int(request.query_params.get("limit", 500))

        # Run in thread pool since this is CPU-bound
        future = _thread_pool.submit(
            IndicatorService.compute, real_symbol, timeframe, exchange, ind_list, limit
        )
        return Response(future.result(timeout=30))


class RegimeCurrentAllView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_regime_service()
        return Response(service.get_all_current_regimes())


class RegimeCurrentView(APIView):
    def get(self, request: Request, symbol: str) -> Response:
        service = _get_regime_service()
        result = service.get_current_regime(symbol)
        if result is None:
            return Response({
                "symbol": symbol, "regime": "unknown", "confidence": 0.0,
                "adx_value": 0.0, "bb_width_percentile": 0.0, "ema_slope": 0.0,
                "trend_alignment": 0.0, "price_structure_score": 0.0,
            })
        return Response(result)


class RegimeHistoryView(APIView):
    def get(self, request: Request, symbol: str) -> Response:
        limit = int(request.query_params.get("limit", 100))
        service = _get_regime_service()
        return Response(service.get_regime_history(symbol, limit))


class RegimeRecommendationView(APIView):
    def get(self, request: Request, symbol: str) -> Response:
        service = _get_regime_service()
        result = service.get_recommendation(symbol)
        if result is None:
            return Response({
                "symbol": symbol, "regime": "unknown", "confidence": 0.0,
                "primary_strategy": "none", "weights": [],
                "position_size_modifier": 0.0, "reasoning": "No data available",
            })
        return Response(result)


class RegimeRecommendationAllView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_regime_service()
        return Response(service.get_all_recommendations())


class RegimePositionSizeView(APIView):
    def post(self, request: Request) -> Response:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.risk.risk_manager import RiskManager

        symbol = request.data.get("symbol", "")
        entry_price = float(request.data.get("entry_price", 0))
        stop_loss_price = float(request.data.get("stop_loss_price", 0))

        service = _get_regime_service()
        risk_manager = RiskManager()
        result = service.get_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_manager=risk_manager,
        )
        if result is None:
            return Response({
                "symbol": symbol, "regime": "unknown", "regime_modifier": 0.0,
                "position_size": 0.0, "entry_price": entry_price,
                "stop_loss_price": stop_loss_price, "primary_strategy": "none",
            })
        return Response(result)


# Singleton regime service
_regime_service = None


def _get_regime_service():
    global _regime_service
    if _regime_service is None:
        from market.services.regime import RegimeService

        _regime_service = RegimeService()
    return _regime_service
