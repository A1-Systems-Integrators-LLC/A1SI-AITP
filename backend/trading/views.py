import threading
import time
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import safe_int as _safe_int
from trading.models import Order, OrderStatus, TradingMode
from trading.serializers import (
    CancelAllResponseSerializer,
    CancelAllSerializer,
    ExchangeHealthSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    SymbolPerformanceSerializer,
    TradingPerformanceFilterSerializer,
    TradingPerformanceSummarySerializer,
)

# Cached exchange connectivity check for LiveTradingStatusView
_exchange_check_cache: dict[str, object] = {
    "ok": False,
    "error": "",
    "checked_at": 0.0,
}
_exchange_check_ttl = 30  # seconds
_exchange_check_lock = threading.Lock()


class OrderListView(APIView):
    @extend_schema(responses=OrderSerializer(many=True), tags=["Trading"])
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        mode = request.query_params.get("mode")
        asset_class = request.query_params.get("asset_class")
        qs = Order.objects.prefetch_related("fill_events").all()
        if mode in ("paper", "live"):
            qs = qs.filter(mode=mode)
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)

        # Symbol filter
        symbol = request.query_params.get("symbol")
        if symbol:
            qs = qs.filter(symbol__icontains=symbol)

        # Status filter
        status_filter = request.query_params.get("status")
        if status_filter:
            valid_statuses = {s.value for s in OrderStatus}
            if status_filter in valid_statuses:
                qs = qs.filter(status=status_filter)

        # Date range filters
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)

        orders = qs[:limit]
        return Response(OrderSerializer(orders, many=True).data)

    @extend_schema(
        request=OrderCreateSerializer,
        responses=OrderSerializer,
        tags=["Trading"],
    )
    def post(self, request: Request) -> Response:
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        mode = data.pop("mode", "paper")
        stop_loss = data.pop("stop_loss_price", None)
        asset_class = data.pop("asset_class", "crypto")

        order = Order.objects.create(
            **data,
            mode=mode,
            asset_class=asset_class,
            stop_loss_price=stop_loss,
            status=OrderStatus.PENDING,
            timestamp=datetime.now(timezone.utc),
        )

        if mode == TradingMode.LIVE:
            from trading.services.live_trading import LiveTradingService
            from trading.services.order_sync import start_order_sync

            order = async_to_sync(LiveTradingService.submit_order)(order)
            async_to_sync(start_order_sync)()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    @extend_schema(responses=OrderSerializer, tags=["Trading"])
    def get(self, request: Request, order_id: int) -> Response:
        try:
            order = Order.objects.prefetch_related("fill_events").get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderSerializer(order).data)


class OrderCancelView(APIView):
    @extend_schema(responses=OrderSerializer, tags=["Trading"])
    def post(self, request: Request, order_id: int) -> Response:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        terminal = {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.ERROR,
        }
        if order.status in terminal:
            return Response(
                {"error": f"Cannot cancel order in '{order.status}' status"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if order.mode == TradingMode.LIVE and order.exchange_order_id:
            from trading.services.live_trading import LiveTradingService

            order = async_to_sync(LiveTradingService.cancel_order)(order)
        else:
            order.transition_to(OrderStatus.CANCELLED)

        return Response(OrderSerializer(order).data)


class LiveTradingStatusView(APIView):
    @extend_schema(tags=["Trading"])
    def get(self, request: Request) -> Response:
        from risk.models import RiskState

        portfolio_id = _safe_int(request.query_params.get("portfolio_id"), 1)

        state = RiskState.objects.filter(portfolio_id=portfolio_id).first()
        is_halted = state.is_halted if state else False

        # Use cached exchange connectivity check (TTL-based)
        exchange_ok, exchange_error = _get_cached_exchange_status()

        active_count = Order.objects.filter(
            mode=TradingMode.LIVE,
            status__in=[
                OrderStatus.SUBMITTED,
                OrderStatus.OPEN,
                OrderStatus.PARTIAL_FILL,
            ],
        ).count()

        return Response(
            {
                "exchange_connected": exchange_ok,
                "exchange_error": exchange_error,
                "is_halted": is_halted,
                "active_live_orders": active_count,
            }
        )


def _get_cached_exchange_status() -> tuple[bool, str]:
    """Return cached exchange connectivity status, refreshing if TTL expired."""
    now = time.monotonic()
    if now - _exchange_check_cache["checked_at"] < _exchange_check_ttl:
        return _exchange_check_cache["ok"], _exchange_check_cache["error"]

    with _exchange_check_lock:
        # Double-check after acquiring lock
        if now - _exchange_check_cache["checked_at"] < _exchange_check_ttl:
            return _exchange_check_cache["ok"], _exchange_check_cache["error"]

        from market.services.exchange import ExchangeService

        async def _check_exchange():
            service = ExchangeService()
            try:
                exchange = await service._get_exchange()
                await exchange.load_markets()
                return True, ""
            except Exception as e:
                return False, str(e)[:200]
            finally:
                await service.close()

        ok, error = async_to_sync(_check_exchange)()
        _exchange_check_cache["ok"] = ok
        _exchange_check_cache["error"] = error
        _exchange_check_cache["checked_at"] = time.monotonic()
        return ok, error


class OrderExportView(APIView):
    @extend_schema(tags=["Trading"])
    def get(self, request: Request) -> Response:
        import csv
        import io

        from django.http import HttpResponse as DjangoHttpResponse

        qs = Order.objects.all()
        mode = request.query_params.get("mode")
        if mode in ("paper", "live"):
            qs = qs.filter(mode=mode)
        asset_class = request.query_params.get("asset_class")
        if asset_class in ("crypto", "equity", "forex"):
            qs = qs.filter(asset_class=asset_class)
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "symbol", "asset_class", "side", "order_type", "amount",
            "price", "avg_fill_price", "filled", "fee", "status", "mode",
            "timestamp", "filled_at",
        ])
        for o in qs.iterator():
            writer.writerow([
                o.id, o.symbol, o.asset_class, o.side, o.order_type, o.amount,
                o.price, o.avg_fill_price, o.filled, o.fee, o.status, o.mode,
                o.timestamp.isoformat() if o.timestamp else "",
                o.filled_at.isoformat() if o.filled_at else "",
            ])

        response = DjangoHttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="orders_export.csv"'
        return response


class TradingPerformanceSummaryView(APIView):
    @extend_schema(
        responses=TradingPerformanceSummarySerializer,
        tags=["Trading"],
    )
    def get(self, request: Request) -> Response:
        from trading.services.performance import TradingPerformanceService

        ser = TradingPerformanceFilterSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        result = TradingPerformanceService.get_summary(
            portfolio_id=d.get("portfolio_id", 1),
            mode=d.get("mode"),
            asset_class=d.get("asset_class"),
            date_from=d.get("date_from"),
            date_to=d.get("date_to"),
        )
        return Response(result)


class TradingPerformanceBySymbolView(APIView):
    @extend_schema(
        responses=SymbolPerformanceSerializer(many=True),
        tags=["Trading"],
    )
    def get(self, request: Request) -> Response:
        from trading.services.performance import TradingPerformanceService

        ser = TradingPerformanceFilterSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        results = TradingPerformanceService.get_by_symbol(
            portfolio_id=d.get("portfolio_id", 1),
            mode=d.get("mode"),
            asset_class=d.get("asset_class"),
            date_from=d.get("date_from"),
            date_to=d.get("date_to"),
        )
        return Response(results)


class PaperTradingStatusView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(service.get_status())


class PaperTradingStartView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def post(self, request: Request) -> Response:
        strategy = request.data.get("strategy", "CryptoInvestorV1")
        service = _get_paper_trading_service()
        return Response(service.start(strategy=strategy))


class PaperTradingStopView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def post(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(service.stop())


class PaperTradingTradesView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_open_trades)())


class PaperTradingHistoryView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_trade_history)(limit))


class PaperTradingProfitView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_profit)())


class PaperTradingPerformanceView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_performance)())


class PaperTradingBalanceView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_balance)())


class PaperTradingLogView(APIView):
    @extend_schema(tags=["Paper Trading"])
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 100, max_val=500)
        service = _get_paper_trading_service()
        return Response(service.get_log_entries(limit))


class CancelAllOrdersView(APIView):
    @extend_schema(
        request=CancelAllSerializer,
        responses=CancelAllResponseSerializer,
        tags=["Trading"],
    )
    def post(self, request: Request) -> Response:
        ser = CancelAllSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        portfolio_id = ser.validated_data["portfolio_id"]

        from portfolio.models import Portfolio

        if not Portfolio.objects.filter(id=portfolio_id).exists():
            return Response(
                {"error": "Portfolio not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from trading.services.live_trading import LiveTradingService

        cancelled = async_to_sync(LiveTradingService.cancel_all_open_orders)(portfolio_id)

        # Audit log entry
        from risk.models import AlertLog

        username = request.user.get_username() if request.user.is_authenticated else "anonymous"
        AlertLog.objects.create(
            portfolio_id=portfolio_id,
            event_type="cancel_all_orders",
            severity="warning",
            message=f"Cancelled {cancelled} orders for portfolio {portfolio_id} by {username}",
        )

        return Response({"cancelled_count": cancelled, "portfolio_id": portfolio_id})


class ExchangeHealthView(APIView):
    @extend_schema(responses=ExchangeHealthSerializer, tags=["Trading"])
    def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService

        exchange_id = request.query_params.get("exchange_id", "binance")
        start = time.monotonic()

        async def _check():
            service = ExchangeService(exchange_id=exchange_id)
            try:
                exchange = await service._get_exchange()
                await exchange.load_markets()
                return True, ""
            except Exception as e:
                return False, str(e)[:200]
            finally:
                await service.close()

        connected, error = async_to_sync(_check)()
        latency_ms = (time.monotonic() - start) * 1000

        return Response({
            "exchange_id": exchange_id,
            "connected": connected,
            "latency_ms": round(latency_ms, 1),
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "error": error if not connected else None,
        })


# Singleton paper trading service
_paper_trading_service = None
_paper_trading_lock = __import__("threading").Lock()


def _get_paper_trading_service():
    global _paper_trading_service
    if _paper_trading_service is None:
        with _paper_trading_lock:
            if _paper_trading_service is None:
                from trading.services.paper_trading import PaperTradingService

                _paper_trading_service = PaperTradingService()
    return _paper_trading_service
