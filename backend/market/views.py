"""Market views — exchange info, tickers, OHLCV, indicators, regime, exchange configs."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import safe_int as _safe_int
from market.models import DataSourceConfig, ExchangeConfig
from market.serializers import (
    DataSourceConfigCreateSerializer,
    DataSourceConfigSerializer,
    ExchangeConfigCreateSerializer,
    ExchangeConfigSerializer,
    ExchangeConfigUpdateSerializer,
    ExchangeInfoSerializer,
    ExchangeTestResultSerializer,
    OHLCVDataSerializer,
    RegimeHistoryEntrySerializer,
    RegimePositionSizeRequestSerializer,
    RegimePositionSizeResponseSerializer,
    RegimeStateSerializer,
    RoutingDecisionSerializer,
    TickerDataSerializer,
)

logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indicator")


# ── Exchange Config CRUD ─────────────────────────────────────


class ExchangeConfigListView(APIView):
    @extend_schema(
        responses=ExchangeConfigSerializer(many=True), tags=["Market"]
    )
    def get(self, request: Request) -> Response:
        configs = ExchangeConfig.objects.all()
        serializer = ExchangeConfigSerializer(configs, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=ExchangeConfigCreateSerializer,
        responses=ExchangeConfigSerializer,
        tags=["Market"],
    )
    def post(self, request: Request) -> Response:
        serializer = ExchangeConfigCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            ExchangeConfigSerializer(instance).data, status=status.HTTP_201_CREATED
        )


class ExchangeConfigDetailView(APIView):
    def _get_object(self, pk: int) -> ExchangeConfig | None:
        try:
            return ExchangeConfig.objects.get(pk=pk)
        except ExchangeConfig.DoesNotExist:
            return None

    @extend_schema(responses=ExchangeConfigSerializer, tags=["Market"])
    def get(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(ExchangeConfigSerializer(obj).data)

    @extend_schema(
        request=ExchangeConfigUpdateSerializer,
        responses=ExchangeConfigSerializer,
        tags=["Market"],
    )
    def put(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = ExchangeConfigUpdateSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(ExchangeConfigSerializer(instance).data)

    @extend_schema(tags=["Market"])
    def delete(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExchangeConfigTestView(APIView):
    @extend_schema(responses=ExchangeTestResultSerializer, tags=["Market"])
    def post(self, request: Request, pk: int) -> Response:
        import asyncio

        import ccxt.async_support as ccxt

        try:
            config = ExchangeConfig.objects.get(pk=pk)
        except ExchangeConfig.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        async def _test_connection():
            exchange_class = getattr(ccxt, config.exchange_id)
            ccxt_config: dict[str, object] = {"enableRateLimit": True}
            if config.api_key:
                ccxt_config["apiKey"] = config.api_key
                ccxt_config["secret"] = config.api_secret
            if config.passphrase:
                ccxt_config["password"] = config.passphrase
            if config.is_sandbox:
                ccxt_config["sandbox"] = True
            if config.options:
                ccxt_config["options"] = config.options

            exchange = exchange_class(ccxt_config)
            try:
                if config.is_sandbox:
                    exchange.set_sandbox_mode(True)
                await exchange.load_markets()
                return True, len(exchange.markets), ""
            except Exception as e:
                return False, 0, str(e)[:500]
            finally:
                await exchange.close()

        loop = asyncio.new_event_loop()
        try:
            success, markets_count, error_msg = loop.run_until_complete(_test_connection())
        finally:
            loop.close()

        now = datetime.now(tz=timezone.utc)
        ExchangeConfig.objects.filter(pk=pk).update(
            last_tested_at=now,
            last_test_success=success,
            last_test_error=error_msg,
        )

        if success:
            return Response({
                "success": True,
                "markets_count": markets_count,
                "message": (
                    f"Connected to {config.exchange_id}"
                    f" — {markets_count} markets loaded"
                ),
            })
        return Response(
            {"success": False, "message": error_msg},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ── Data Source Config CRUD ──────────────────────────────────


class DataSourceConfigListView(APIView):
    @extend_schema(
        responses=DataSourceConfigSerializer(many=True), tags=["Market"]
    )
    def get(self, request: Request) -> Response:
        sources = DataSourceConfig.objects.select_related("exchange_config").all()
        serializer = DataSourceConfigSerializer(sources, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=DataSourceConfigCreateSerializer,
        responses=DataSourceConfigSerializer,
        tags=["Market"],
    )
    def post(self, request: Request) -> Response:
        serializer = DataSourceConfigCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        read_serializer = DataSourceConfigSerializer(instance)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


class DataSourceConfigDetailView(APIView):
    def _get_object(self, pk: int):
        try:
            return DataSourceConfig.objects.select_related("exchange_config").get(pk=pk)
        except DataSourceConfig.DoesNotExist:
            return None

    @extend_schema(responses=DataSourceConfigSerializer, tags=["Market"])
    def get(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(DataSourceConfigSerializer(obj).data)

    @extend_schema(
        request=DataSourceConfigCreateSerializer,
        responses=DataSourceConfigSerializer,
        tags=["Market"],
    )
    def put(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DataSourceConfigCreateSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(DataSourceConfigSerializer(instance).data)

    @extend_schema(tags=["Market"])
    def delete(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Existing views ───────────────────────────────────────────


class ExchangeListView(APIView):
    @extend_schema(
        responses=ExchangeInfoSerializer(many=True), tags=["Market"]
    )
    def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService

        service = ExchangeService()
        return Response(service.list_exchanges())


class TickerView(APIView):
    @extend_schema(responses=TickerDataSerializer, tags=["Market"])
    def get(self, request: Request, symbol: str) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.exchange import ExchangeService

        async def _fetch():
            service = ExchangeService()
            try:
                return await service.fetch_ticker(symbol)
            finally:
                await service.close()

        return Response(async_to_sync(_fetch)())


class TickerListView(APIView):
    @extend_schema(
        responses=TickerDataSerializer(many=True), tags=["Market"]
    )
    def get(self, request: Request) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.exchange import ExchangeService

        symbols_param = request.query_params.get("symbols")
        symbol_list = symbols_param.split(",") if symbols_param else None

        async def _fetch():
            service = ExchangeService()
            try:
                return await service.fetch_tickers(symbol_list)
            finally:
                await service.close()

        return Response(async_to_sync(_fetch)())


class OHLCVView(APIView):
    @extend_schema(
        responses=OHLCVDataSerializer(many=True), tags=["Market"]
    )
    def get(self, request: Request, symbol: str) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.exchange import ExchangeService

        timeframe = request.query_params.get("timeframe", "1h")
        limit = _safe_int(request.query_params.get("limit"), 100, max_val=1000)

        async def _fetch():
            service = ExchangeService()
            try:
                return await service.fetch_ohlcv(symbol, timeframe, limit)
            finally:
                await service.close()

        return Response(async_to_sync(_fetch)())


class IndicatorListView(APIView):
    @extend_schema(tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.indicators import IndicatorService

        return Response(IndicatorService.list_available())


class IndicatorComputeView(APIView):
    @extend_schema(tags=["Market"])
    def get(self, request: Request, exchange: str, symbol: str, timeframe: str) -> Response:
        from market.services.indicators import IndicatorService

        real_symbol = symbol.replace("_", "/")
        indicators_param = request.query_params.get("indicators", "")
        ind_list = (
            [i.strip() for i in indicators_param.split(",") if i.strip()]
            if indicators_param
            else None
        )
        limit = _safe_int(request.query_params.get("limit"), 500, max_val=2000)

        # Run in thread pool since this is CPU-bound
        future = _thread_pool.submit(
            IndicatorService.compute, real_symbol, timeframe, exchange, ind_list, limit
        )
        return Response(future.result(timeout=30))


class RegimeCurrentAllView(APIView):
    @extend_schema(
        responses=RegimeStateSerializer(many=True), tags=["Regime"]
    )
    def get(self, request: Request) -> Response:
        service = _get_regime_service()
        return Response(service.get_all_current_regimes())


class RegimeCurrentView(APIView):
    @extend_schema(responses=RegimeStateSerializer, tags=["Regime"])
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
    @extend_schema(
        responses=RegimeHistoryEntrySerializer(many=True), tags=["Regime"]
    )
    def get(self, request: Request, symbol: str) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 100, max_val=1000)
        service = _get_regime_service()
        return Response(service.get_regime_history(symbol, limit))


class RegimeRecommendationView(APIView):
    @extend_schema(responses=RoutingDecisionSerializer, tags=["Regime"])
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
    @extend_schema(
        responses=RoutingDecisionSerializer(many=True), tags=["Regime"]
    )
    def get(self, request: Request) -> Response:
        service = _get_regime_service()
        return Response(service.get_all_recommendations())


class RegimePositionSizeView(APIView):
    @extend_schema(
        request=RegimePositionSizeRequestSerializer,
        responses=RegimePositionSizeResponseSerializer,
        tags=["Regime"],
    )
    def post(self, request: Request) -> Response:
        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.risk.risk_manager import RiskManager

        symbol = request.data.get("symbol", "")
        try:
            entry_price = float(request.data.get("entry_price", 0))
            stop_loss_price = float(request.data.get("stop_loss_price", 0))
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid entry_price or stop_loss_price"},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
