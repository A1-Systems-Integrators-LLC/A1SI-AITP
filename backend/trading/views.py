from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from trading.models import Order, OrderStatus, TradingMode
from trading.serializers import OrderCreateSerializer, OrderSerializer


def _safe_int(value: str | None, default: int, min_val: int = 1, max_val: int = 1000) -> int:
    """Safely convert a query parameter to int with bounds."""
    if value is None:
        return default
    try:
        return max(min_val, min(int(value), max_val))
    except (ValueError, TypeError):
        return default


class OrderListView(APIView):
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        mode = request.query_params.get("mode")
        qs = Order.objects.all()
        if mode in ("paper", "live"):
            qs = qs.filter(mode=mode)
        orders = qs[:limit]
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request: Request) -> Response:
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        mode = data.pop("mode", "paper")
        stop_loss = data.pop("stop_loss_price", None)

        order = Order.objects.create(
            **data,
            mode=mode,
            stop_loss_price=stop_loss,
            status=OrderStatus.PENDING,
            timestamp=datetime.now(timezone.utc),
        )

        if mode == TradingMode.LIVE:
            from trading.services.live_trading import LiveTradingService
            from trading.services.order_sync import start_order_sync

            order = async_to_sync(LiveTradingService.submit_order)(order)
            async_to_sync(start_order_sync)()

        return Response(
            OrderSerializer(order).data, status=status.HTTP_201_CREATED
        )


class OrderDetailView(APIView):
    def get(self, request: Request, order_id: int) -> Response:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(OrderSerializer(order).data)


class OrderCancelView(APIView):
    def post(self, request: Request, order_id: int) -> Response:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )

        terminal = {
            OrderStatus.FILLED, OrderStatus.CANCELLED,
            OrderStatus.REJECTED, OrderStatus.ERROR,
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
    def get(self, request: Request) -> Response:
        from market.services.exchange import ExchangeService
        from risk.models import RiskState

        portfolio_id = _safe_int(request.query_params.get("portfolio_id"), 1)

        state = RiskState.objects.filter(portfolio_id=portfolio_id).first()
        is_halted = state.is_halted if state else False

        exchange_ok = False
        exchange_error = ""

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

        exchange_ok, exchange_error = async_to_sync(_check_exchange)()

        active_count = Order.objects.filter(
            mode=TradingMode.LIVE,
            status__in=[
                OrderStatus.SUBMITTED, OrderStatus.OPEN,
                OrderStatus.PARTIAL_FILL,
            ],
        ).count()

        return Response({
            "exchange_connected": exchange_ok,
            "exchange_error": exchange_error,
            "is_halted": is_halted,
            "active_live_orders": active_count,
        })


class PaperTradingStatusView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(service.get_status())


class PaperTradingStartView(APIView):
    def post(self, request: Request) -> Response:
        strategy = request.data.get("strategy", "CryptoInvestorV1")
        service = _get_paper_trading_service()
        return Response(service.start(strategy=strategy))


class PaperTradingStopView(APIView):
    def post(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(service.stop())


class PaperTradingTradesView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_open_trades)())


class PaperTradingHistoryView(APIView):
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_trade_history)(limit))


class PaperTradingProfitView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_profit)())


class PaperTradingPerformanceView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_performance)())


class PaperTradingBalanceView(APIView):
    def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(async_to_sync(service.get_balance)())


class PaperTradingLogView(APIView):
    def get(self, request: Request) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 100, max_val=500)
        service = _get_paper_trading_service()
        return Response(service.get_log_entries(limit))


# Singleton paper trading service
_paper_trading_service = None


def _get_paper_trading_service():
    global _paper_trading_service
    if _paper_trading_service is None:
        from trading.services.paper_trading import PaperTradingService

        _paper_trading_service = PaperTradingService()
    return _paper_trading_service
