"""Market views — exchange info, tickers, OHLCV, indicators, regime, exchange configs."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from ccxt.base.errors import ExchangeNotAvailable, NetworkError, RequestTimeout
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.error_response import error_response
from core.utils import safe_int as _safe_int
from market.models import DataSourceConfig, ExchangeConfig
from market.serializers import (
    CircuitBreakerListResponseSerializer,
    CircuitBreakerResetSerializer,
    DataSourceConfigCreateSerializer,
    DataSourceConfigSerializer,
    ExchangeConfigCreateSerializer,
    ExchangeConfigSerializer,
    ExchangeConfigUpdateSerializer,
    ExchangeInfoSerializer,
    ExchangeTestResultSerializer,
    IndicatorInfoSerializer,
    KeyRotationResponseSerializer,
    MarketStatusSerializer,
    NewsArticleSerializer,
    NewsFetchResponseSerializer,
    NewsSentimentSummarySerializer,
    OHLCVDataSerializer,
    RegimeHistoryEntrySerializer,
    RegimePositionSizeRequestSerializer,
    RegimePositionSizeResponseSerializer,
    RegimeStateSerializer,
    RoutingDecisionSerializer,
    SentimentSignalSerializer,
    TickerDataSerializer,
)

logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="indicator")


# ── News views ──────────────────────────────────────────────


class NewsListView(APIView):
    @extend_schema(responses=NewsArticleSerializer(many=True), tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.news import NewsService

        asset_class = request.query_params.get("asset_class")
        symbol = request.query_params.get("symbol")
        limit = _safe_int(request.query_params.get("limit"), 20, max_val=100)

        service = NewsService()
        articles = service.get_articles(asset_class, symbol, limit)
        return Response(articles)


class NewsSentimentView(APIView):
    @extend_schema(responses=NewsSentimentSummarySerializer, tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.news import NewsService

        asset_class = request.query_params.get("asset_class")
        hours = _safe_int(request.query_params.get("hours"), 24, max_val=168)

        service = NewsService()
        summary = service.get_sentiment_summary(asset_class, hours)
        return Response(summary)


class SentimentSignalView(APIView):
    @extend_schema(responses=SentimentSignalSerializer, tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.news import NewsService

        asset_class = request.query_params.get("asset_class", "crypto")
        if asset_class not in ("crypto", "equity", "forex"):
            return Response(
                {"error": "Invalid asset_class"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        hours = _safe_int(request.query_params.get("hours"), 24, max_val=168)

        service = NewsService()
        signal = service.get_sentiment_signal(asset_class, hours)
        return Response(signal)


class NewsFetchView(APIView):
    @extend_schema(responses=NewsFetchResponseSerializer, tags=["Market"])
    def post(self, request: Request) -> Response:
        from market.services.news import NewsService

        asset_class = request.data.get("asset_class", "crypto")
        if asset_class not in ("crypto", "equity", "forex"):
            return Response(
                {"error": "Invalid asset_class"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = NewsService()
        count = service.fetch_and_store(asset_class)
        return Response(
            {
                "asset_class": asset_class,
                "articles_fetched": count,
                "message": f"Fetched {count} new articles for {asset_class}",
            }
        )


# ── Market Status ────────────────────────────────────────────


class MarketStatusView(APIView):
    @extend_schema(responses=MarketStatusSerializer, tags=["Market"])
    def get(self, request: Request) -> Response:
        asset_class = request.query_params.get("asset_class", "crypto")
        if asset_class not in ("crypto", "equity", "forex"):
            return Response(
                {"error": "Invalid asset_class. Must be crypto, equity, or forex."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from core.platform_bridge import ensure_platform_imports

        ensure_platform_imports()
        from common.market_hours.sessions import MarketHoursService

        info = MarketHoursService.get_session_info(asset_class)
        return Response(info)


# ── Exchange Config CRUD ─────────────────────────────────────


class ExchangeConfigListView(APIView):
    @extend_schema(responses=ExchangeConfigSerializer(many=True), tags=["Market"])
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
        return Response(ExchangeConfigSerializer(instance).data, status=status.HTTP_201_CREATED)


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
            return error_response("Exchange config not found", 404)
        return Response(ExchangeConfigSerializer(obj).data)

    @extend_schema(
        request=ExchangeConfigUpdateSerializer,
        responses=ExchangeConfigSerializer,
        tags=["Market"],
    )
    def put(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return error_response("Exchange config not found", 404)
        serializer = ExchangeConfigUpdateSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(ExchangeConfigSerializer(instance).data)

    @extend_schema(responses={204: None}, tags=["Market"])
    def delete(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return error_response("Exchange config not found", 404)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExchangeConfigTestView(APIView):
    @extend_schema(responses=ExchangeTestResultSerializer, tags=["Market"])
    def post(self, request: Request, pk: int) -> Response:
        import ccxt.async_support as ccxt
        from asgiref.sync import async_to_sync

        try:
            config = ExchangeConfig.objects.get(pk=pk)
        except ExchangeConfig.DoesNotExist:
            return error_response("Exchange config not found", 404)

        async def _test_connection():
            exchange_class = getattr(ccxt, config.exchange_id)
            ccxt_config: dict[str, object] = {"enableRateLimit": True}
            if config.api_key:
                ccxt_config["apiKey"] = config.api_key
                ccxt_config["secret"] = config.api_secret
            if config.passphrase:
                ccxt_config["password"] = config.passphrase
            if config.options:
                ccxt_config["options"] = config.options

            exchange = None
            try:
                exchange = exchange_class(ccxt_config)
                if config.is_sandbox:
                    exchange.set_sandbox_mode(True)
                await exchange.load_markets()
                return True, len(exchange.markets), ""
            except Exception as e:
                return False, 0, str(e)[:500]
            finally:
                if exchange:
                    await exchange.close()

        success, markets_count, error_msg = async_to_sync(_test_connection)()

        now = datetime.now(tz=timezone.utc)
        ExchangeConfig.objects.filter(pk=pk).update(
            last_tested_at=now,
            last_test_success=success,
            last_test_error=error_msg,
        )

        if success:
            return Response(
                {
                    "success": True,
                    "markets_count": markets_count,
                    "message": (
                        f"Connected to {config.exchange_id} — {markets_count} markets loaded"
                    ),
                }
            )
        return Response(
            {"success": False, "message": error_msg},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ExchangeConfigRotateView(APIView):
    """Rotate exchange API keys with validation."""

    @extend_schema(responses=KeyRotationResponseSerializer, tags=["Market"])
    def post(self, request: Request, pk: int) -> Response:
        import ccxt.async_support as ccxt
        from asgiref.sync import async_to_sync

        from market.serializers import ExchangeConfigRotateSerializer

        try:
            config = ExchangeConfig.objects.get(pk=pk)
        except ExchangeConfig.DoesNotExist:
            return error_response("Exchange config not found", 404)

        ser = ExchangeConfigRotateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        new_key = ser.validated_data["api_key"]
        new_secret = ser.validated_data["api_secret"]
        new_passphrase = ser.validated_data.get("passphrase", "")

        # Test new credentials before applying
        async def _test_new_keys():
            exchange_class = getattr(ccxt, config.exchange_id)
            ccxt_config: dict[str, object] = {
                "enableRateLimit": True,
                "apiKey": new_key,
                "secret": new_secret,
            }
            if new_passphrase:
                ccxt_config["password"] = new_passphrase
            if config.options:
                ccxt_config["options"] = config.options

            exchange = None
            try:
                exchange = exchange_class(ccxt_config)
                if config.is_sandbox:
                    exchange.set_sandbox_mode(True)
                await exchange.load_markets()
                return True, len(exchange.markets), ""
            except Exception as e:
                return False, 0, str(e)[:500]
            finally:
                if exchange:
                    await exchange.close()

        success, markets_count, error_msg = async_to_sync(_test_new_keys)()

        if not success:
            return Response(
                {"error": f"New key validation failed: {error_msg}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Atomically update keys
        from django.db import transaction
        from django.utils import timezone

        from risk.models import AlertLog

        now = timezone.now()
        with transaction.atomic():
            config.api_key = new_key
            config.api_secret = new_secret
            if new_passphrase:
                config.passphrase = new_passphrase
            config.key_rotated_at = now
            config.last_tested_at = now
            config.last_test_success = True
            config.last_test_error = ""
            config.save()

            AlertLog.objects.create(
                portfolio_id=0,
                event_type="key_rotation",
                severity="info",
                channel="system",
                message=f"API keys rotated for {config.name} ({config.exchange_id})",
                delivered=True,
            )

        return Response({
            "success": True,
            "markets_count": markets_count,
            "message": f"Keys rotated for {config.name} — {markets_count} markets validated",
            "key_rotated_at": now.isoformat(),
        })


# ── Data Source Config CRUD ──────────────────────────────────


class DataSourceConfigListView(APIView):
    @extend_schema(responses=DataSourceConfigSerializer(many=True), tags=["Market"])
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
            return error_response("Data source config not found", 404)
        return Response(DataSourceConfigSerializer(obj).data)

    @extend_schema(
        request=DataSourceConfigCreateSerializer,
        responses=DataSourceConfigSerializer,
        tags=["Market"],
    )
    def put(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return error_response("Data source config not found", 404)
        serializer = DataSourceConfigCreateSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(DataSourceConfigSerializer(instance).data)

    @extend_schema(tags=["Market"])
    def delete(self, request: Request, pk: int) -> Response:
        obj = self._get_object(pk)
        if obj is None:
            return error_response("Data source config not found", 404)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Existing views ───────────────────────────────────────────


class ExchangeListView(APIView):
    @extend_schema(responses=ExchangeInfoSerializer(many=True), tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService

        service = ExchangeService()
        return Response(service.list_exchanges())


class TickerView(APIView):
    @extend_schema(responses=TickerDataSerializer, tags=["Market"])
    def get(self, request: Request, symbol: str) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.data_router import DataServiceRouter

        asset_class = request.query_params.get("asset_class", "crypto")
        router = DataServiceRouter()
        try:
            return Response(async_to_sync(router.fetch_ticker)(symbol, asset_class))
        except (RequestTimeout, asyncio.TimeoutError) as exc:
            logger.warning("Ticker timeout for %s: %s", symbol, exc)
            return error_response(f"Request timed out fetching ticker for {symbol}", 408)
        except (ExchangeNotAvailable, NetworkError) as exc:
            logger.warning("Exchange unavailable for ticker %s: %s", symbol, exc)
            return error_response(f"Exchange unavailable: {exc}", 503)
        except Exception as exc:
            logger.warning("Ticker fetch failed for %s: %s", symbol, exc)
            return error_response(f"Failed to fetch ticker for {symbol}: {exc}", 500)


class TickerListView(APIView):
    @extend_schema(
        responses=TickerDataSerializer(many=True),
        tags=["Market"],
        parameters=[
            OpenApiParameter("symbols", str, description="Comma-separated symbol list (max 50)"),
            OpenApiParameter(
                "asset_class",
                str,
                description="Asset class (default: crypto)",
                enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.exchange import ExchangeService

        symbols_param = request.query_params.get("symbols")
        symbol_list = symbols_param.split(",") if symbols_param else None
        asset_class = request.query_params.get("asset_class", "crypto")

        if symbol_list and len(symbol_list) > 50:
            return Response(
                {"error": "Too many symbols. Maximum 50 per request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if asset_class in ("equity", "forex"):
                from market.services.data_router import DataServiceRouter

                router = DataServiceRouter()
                return Response(
                    async_to_sync(router.fetch_tickers)(
                        symbol_list,
                        asset_class,
                    )
                )

            async def _fetch():
                service = ExchangeService()
                try:
                    return await service.fetch_tickers(symbol_list)
                finally:
                    await service.close()

            return Response(async_to_sync(_fetch)())
        except (RequestTimeout, asyncio.TimeoutError) as exc:
            logger.warning("Tickers timeout: %s", exc)
            return error_response("Request timed out fetching tickers", 408)
        except (ExchangeNotAvailable, NetworkError) as exc:
            logger.warning("Exchange unavailable for tickers: %s", exc)
            return error_response(f"Exchange unavailable: {exc}", 503)
        except Exception as exc:
            logger.warning("Tickers fetch failed: %s", exc)
            return error_response(f"Failed to fetch tickers: {exc}", 500)


class OHLCVView(APIView):
    @extend_schema(
        responses=OHLCVDataSerializer(many=True),
        tags=["Market"],
        parameters=[
            OpenApiParameter(
                "timeframe",
                str,
                description="Candlestick timeframe (default: 1h)",
                enum=["1m", "5m", "15m", "1h", "4h", "1d"],
            ),
            OpenApiParameter("limit", int, description="Max candles (default 100, max 1000)"),
            OpenApiParameter(
                "asset_class",
                str,
                description="Asset class (default: crypto)",
                enum=["crypto", "equity", "forex"],
            ),
        ],
    )
    def get(self, request: Request, symbol: str) -> Response:
        from asgiref.sync import async_to_sync

        from market.services.data_router import DataServiceRouter

        timeframe = request.query_params.get("timeframe", "1h")
        limit = _safe_int(request.query_params.get("limit"), 100, max_val=1000)
        asset_class = request.query_params.get("asset_class", "crypto")

        router = DataServiceRouter()
        try:
            return Response(
                async_to_sync(router.fetch_ohlcv)(
                    symbol,
                    timeframe,
                    limit,
                    asset_class,
                )
            )
        except (RequestTimeout, asyncio.TimeoutError) as exc:
            logger.warning("OHLCV timeout for %s: %s", symbol, exc)
            return error_response(f"Request timed out fetching OHLCV for {symbol}", 408)
        except (ExchangeNotAvailable, NetworkError) as exc:
            logger.warning("Exchange unavailable for OHLCV %s: %s", symbol, exc)
            return error_response(f"Exchange unavailable: {exc}", 503)
        except Exception as exc:
            logger.warning("OHLCV fetch failed for %s: %s", symbol, exc)
            return error_response(f"Failed to fetch OHLCV for {symbol}: {exc}", 500)


class IndicatorListView(APIView):
    @extend_schema(responses=IndicatorInfoSerializer(many=True), tags=["Market"])
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
        try:
            return Response(future.result(timeout=30))
        except TimeoutError:
            future.cancel()
            return Response(
                {"error": "Indicator computation timed out after 30 seconds"},
                status=status.HTTP_408_REQUEST_TIMEOUT,
            )


class RegimeCurrentAllView(APIView):
    @extend_schema(responses=RegimeStateSerializer(many=True), tags=["Regime"])
    def get(self, request: Request) -> Response:
        service = _get_regime_service()
        return Response(service.get_all_current_regimes())


class RegimeCurrentView(APIView):
    @extend_schema(responses=RegimeStateSerializer, tags=["Regime"])
    def get(self, request: Request, symbol: str) -> Response:
        service = _get_regime_service()
        result = service.get_current_regime(symbol)
        if result is None:
            return Response(
                {
                    "symbol": symbol,
                    "regime": "unknown",
                    "confidence": 0.0,
                    "adx_value": 0.0,
                    "bb_width_percentile": 0.0,
                    "ema_slope": 0.0,
                    "trend_alignment": 0.0,
                    "price_structure_score": 0.0,
                }
            )
        return Response(result)


class RegimeHistoryView(APIView):
    @extend_schema(responses=RegimeHistoryEntrySerializer(many=True), tags=["Regime"])
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
            return Response(
                {
                    "symbol": symbol,
                    "regime": "unknown",
                    "confidence": 0.0,
                    "primary_strategy": "none",
                    "weights": [],
                    "position_size_modifier": 0.0,
                    "reasoning": "No data available",
                }
            )
        return Response(result)


class RegimeRecommendationAllView(APIView):
    @extend_schema(responses=RoutingDecisionSerializer(many=True), tags=["Regime"])
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

        ser = RegimePositionSizeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        ensure_platform_imports()
        from common.risk.risk_manager import RiskManager

        symbol = ser.validated_data["symbol"]
        entry_price = ser.validated_data["entry_price"]
        stop_loss_price = ser.validated_data["stop_loss_price"]

        service = _get_regime_service()
        risk_manager = RiskManager()
        result = service.get_position_size(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            risk_manager=risk_manager,
        )
        if result is None:
            return Response(
                {
                    "symbol": symbol,
                    "regime": "unknown",
                    "regime_modifier": 0.0,
                    "position_size": 0.0,
                    "entry_price": entry_price,
                    "stop_loss_price": stop_loss_price,
                    "primary_strategy": "none",
                }
            )
        return Response(result)


# ── Circuit Breaker ──────────────────────────────────────────


class CircuitBreakerStatusView(APIView):
    @extend_schema(responses=CircuitBreakerListResponseSerializer, tags=["Market"])
    def get(self, request: Request) -> Response:
        from market.services.circuit_breaker import get_all_breakers

        return Response({"breakers": get_all_breakers()})

    @extend_schema(responses=CircuitBreakerResetSerializer, tags=["Market"])
    def post(self, request: Request) -> Response:
        from market.services.circuit_breaker import reset_breaker

        exchange_id = request.data.get("exchange_id")
        action = request.data.get("action")
        if not exchange_id or action != "reset":
            return Response(
                {"error": "Provide exchange_id and action='reset'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if reset_breaker(exchange_id):
            return Response({"message": f"Circuit breaker for {exchange_id} reset"})
        return Response(
            {"error": f"No breaker found for {exchange_id}"},
            status=status.HTTP_404_NOT_FOUND,
        )


# Singleton regime service
_regime_service = None
_regime_service_lock = __import__("threading").Lock()


def _get_regime_service():
    global _regime_service
    if _regime_service is None:
        with _regime_service_lock:
            if _regime_service is None:
                from market.services.regime import RegimeService

                _regime_service = RegimeService()
    return _regime_service
