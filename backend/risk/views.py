"""Risk management views."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.utils import safe_int as _safe_int
from risk.serializers import (
    AlertLogSerializer,
    EquityUpdateSerializer,
    HaltRequestSerializer,
    HaltResponseSerializer,
    HeatCheckResponseSerializer,
    PositionSizeRequestSerializer,
    PositionSizeResponseSerializer,
    RiskLimitChangeSerializer,
    RiskLimitsSerializer,
    RiskLimitsUpdateSerializer,
    RiskMetricHistorySerializer,
    RiskStatusSerializer,
    TradeCheckLogSerializer,
    TradeCheckRequestSerializer,
    TradeCheckResponseSerializer,
    VaRResponseSerializer,
)
from risk.services.risk import RiskManagementService


class RiskStatusView(APIView):
    @extend_schema(responses=RiskStatusSerializer, tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.get_status(portfolio_id))


class RiskLimitsView(APIView):
    @extend_schema(responses=RiskLimitsSerializer, tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        limits = RiskManagementService.get_limits(portfolio_id)
        return Response(RiskLimitsSerializer(limits).data)

    @extend_schema(
        request=RiskLimitsUpdateSerializer,
        responses=RiskLimitsSerializer,
        tags=["Risk"],
    )
    def put(self, request: Request, portfolio_id: int) -> Response:
        ser = RiskLimitsUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # Only include fields that were explicitly sent in the request
        updates = {k: v for k, v in ser.validated_data.items() if k in request.data}
        limits = RiskManagementService.update_limits(
            portfolio_id,
            updates,
            changed_by=request.user.username if request.user.is_authenticated else "",
            reason=request.data.get("reason", ""),
        )
        return Response(RiskLimitsSerializer(limits).data)


class EquityUpdateView(APIView):
    @extend_schema(
        request=EquityUpdateSerializer,
        responses=RiskStatusSerializer,
        tags=["Risk"],
    )
    def post(self, request: Request, portfolio_id: int) -> Response:
        ser = EquityUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        equity = ser.validated_data["equity"]
        return Response(RiskManagementService.update_equity(portfolio_id, equity))


class TradeCheckView(APIView):
    # Allow unauthenticated access for internal Freqtrade risk gate calls.
    # This endpoint only reads risk state and returns approve/reject — no mutations.
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        request=TradeCheckRequestSerializer,
        responses=TradeCheckResponseSerializer,
        tags=["Risk"],
    )
    def post(self, request: Request, portfolio_id: int) -> Response:
        ser = TradeCheckRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        composite_score = d.get("composite_score")
        asset_class = d.get("asset_class", "crypto")
        approved, reason = RiskManagementService.check_trade(
            portfolio_id,
            d["symbol"],
            d["side"],
            d["size"],
            d["entry_price"],
            d.get("stop_loss_price"),
            composite_score=composite_score,
            asset_class=asset_class,
        )
        result = {"approved": approved, "reason": reason}
        if composite_score is not None:
            result["composite_score"] = composite_score
        return Response(result)


class PositionSizeView(APIView):
    @extend_schema(
        request=PositionSizeRequestSerializer,
        responses=PositionSizeResponseSerializer,
        tags=["Risk"],
    )
    def post(self, request: Request, portfolio_id: int) -> Response:
        ser = PositionSizeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        return Response(
            RiskManagementService.calculate_position_size(
                portfolio_id,
                d["entry_price"],
                d["stop_loss_price"],
                d.get("risk_per_trade"),
            ),
        )


class ResetDailyView(APIView):
    @extend_schema(responses=RiskStatusSerializer, tags=["Risk"])
    def post(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.reset_daily(portfolio_id))


class VaRView(APIView):
    @extend_schema(responses=VaRResponseSerializer, tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        method = request.query_params.get("method", "parametric")
        return Response(RiskManagementService.get_var(portfolio_id, method))


class HeatCheckView(APIView):
    @extend_schema(responses=HeatCheckResponseSerializer, tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.get_heat_check(portfolio_id))


class MetricHistoryView(APIView):
    @extend_schema(responses=RiskMetricHistorySerializer(many=True), tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        hours = _safe_int(request.query_params.get("hours"), 168, min_val=1, max_val=8760)
        entries = RiskManagementService.get_metric_history(portfolio_id, hours)
        return Response(RiskMetricHistorySerializer(entries, many=True).data)


class RecordMetricsView(APIView):
    @extend_schema(responses=RiskMetricHistorySerializer, tags=["Risk"])
    def post(self, request: Request, portfolio_id: int) -> Response:
        method = request.query_params.get("method", "parametric")
        entry = RiskManagementService.record_metrics(portfolio_id, method)
        return Response(RiskMetricHistorySerializer(entry).data)


class HaltTradingView(APIView):
    @extend_schema(
        request=HaltRequestSerializer,
        responses=HaltResponseSerializer,
        tags=["Risk"],
    )
    def post(self, request: Request, portfolio_id: int) -> Response:
        from asgiref.sync import async_to_sync

        ser = HaltRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data["reason"]
        result = async_to_sync(RiskManagementService.halt_trading_with_cancellation)(
            portfolio_id, reason,
        )
        return Response(result)


class ResumeTradingView(APIView):
    @extend_schema(responses=HaltResponseSerializer, tags=["Risk"])
    def post(self, request: Request, portfolio_id: int) -> Response:
        from asgiref.sync import async_to_sync

        result = async_to_sync(RiskManagementService.resume_trading_with_broadcast)(portfolio_id)
        return Response(result)


class AlertListView(APIView):
    @extend_schema(
        responses=AlertLogSerializer(many=True),
        tags=["Risk"],
        parameters=[
            OpenApiParameter("limit", int, description="Max results (default 50, max 200)"),
            OpenApiParameter("severity", str, description="Filter by severity level"),
            OpenApiParameter("event_type", str, description="Filter by event type"),
            OpenApiParameter(
                "created_after", str, description="Filter alerts after this ISO datetime",
            ),
            OpenApiParameter(
                "created_before", str, description="Filter alerts before this ISO datetime",
            ),
        ],
    )
    def get(self, request: Request, portfolio_id: int) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        alerts = RiskManagementService.get_alerts(
            portfolio_id,
            limit,
            severity=request.query_params.get("severity"),
            event_type=request.query_params.get("event_type"),
            created_after=request.query_params.get("created_after"),
            created_before=request.query_params.get("created_before"),
        )
        return Response(AlertLogSerializer(alerts, many=True).data)


class TradeLogView(APIView):
    @extend_schema(responses=TradeCheckLogSerializer(many=True), tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        logs = RiskManagementService.get_trade_log(portfolio_id, limit)
        return Response(TradeCheckLogSerializer(logs, many=True).data)


class RiskLimitHistoryView(APIView):
    @extend_schema(responses=RiskLimitChangeSerializer(many=True), tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        from risk.models import RiskLimitChange

        limit = _safe_int(request.query_params.get("limit"), 50, max_val=200)
        qs = RiskLimitChange.objects.filter(portfolio_id=portfolio_id)
        field = request.query_params.get("field")
        if field:
            qs = qs.filter(field_name=field)
        entries = qs.order_by("-changed_at")[:limit]
        return Response(RiskLimitChangeSerializer(entries, many=True).data)


class ProfitTrackingView(APIView):
    """GET /api/risk/{portfolio_id}/profit-tracking/ — profit reinvestment state."""

    @extend_schema(tags=["Risk"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        try:
            from common.risk.profit_tracker import ProfitTracker

            tracker = ProfitTracker.get_instance()
            return Response(tracker.get_summary())
        except Exception as e:
            return Response({"error": str(e)}, status=500)
