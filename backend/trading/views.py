from datetime import datetime, timezone

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from trading.models import Order
from trading.serializers import OrderCreateSerializer, OrderSerializer


class OrderListView(APIView):
    def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit", 50))
        limit = max(1, min(limit, 200))
        orders = Order.objects.all()[:limit]
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request: Request) -> Response:
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = Order.objects.create(
            **ser.validated_data,
            status="created",
            timestamp=datetime.now(timezone.utc),
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    def get(self, request: Request, order_id: int) -> Response:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderSerializer(order).data)


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
    async def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        trades = await service.get_open_trades()
        return Response(trades)


class PaperTradingHistoryView(APIView):
    async def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit", 50))
        service = _get_paper_trading_service()
        trades = await service.get_trade_history(limit)
        return Response(trades)


class PaperTradingProfitView(APIView):
    async def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(await service.get_profit())


class PaperTradingPerformanceView(APIView):
    async def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(await service.get_performance())


class PaperTradingBalanceView(APIView):
    async def get(self, request: Request) -> Response:
        service = _get_paper_trading_service()
        return Response(await service.get_balance())


class PaperTradingLogView(APIView):
    def get(self, request: Request) -> Response:
        limit = int(request.query_params.get("limit", 100))
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
