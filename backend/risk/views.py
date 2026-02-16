"""Risk management views."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from risk.services.risk import RiskManagementService


class RiskStatusView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.get_status(portfolio_id))


class RiskLimitsView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import RiskLimitsSerializer

        limits = RiskManagementService.get_limits(portfolio_id)
        return Response(RiskLimitsSerializer(limits).data)

    def put(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import RiskLimitsSerializer, RiskLimitsUpdateSerializer

        ser = RiskLimitsUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        updates = {k: v for k, v in ser.validated_data.items() if v is not None}
        limits = RiskManagementService.update_limits(portfolio_id, updates)
        return Response(RiskLimitsSerializer(limits).data)


class EquityUpdateView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        equity = float(request.data.get("equity", 0))
        return Response(RiskManagementService.update_equity(portfolio_id, equity))


class TradeCheckView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import TradeCheckRequestSerializer

        ser = TradeCheckRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        approved, reason = RiskManagementService.check_trade(
            portfolio_id, d["symbol"], d["side"], d["size"],
            d["entry_price"], d.get("stop_loss_price"),
        )
        return Response({"approved": approved, "reason": reason})


class PositionSizeView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import PositionSizeRequestSerializer

        ser = PositionSizeRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        return Response(RiskManagementService.calculate_position_size(
            portfolio_id, d["entry_price"], d["stop_loss_price"], d.get("risk_per_trade"),
        ))


class ResetDailyView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.reset_daily(portfolio_id))


class VaRView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        method = request.query_params.get("method", "parametric")
        return Response(RiskManagementService.get_var(portfolio_id, method))


class HeatCheckView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        return Response(RiskManagementService.get_heat_check(portfolio_id))


class MetricHistoryView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import RiskMetricHistorySerializer

        hours = int(request.query_params.get("hours", 168))
        entries = RiskManagementService.get_metric_history(portfolio_id, hours)
        return Response(RiskMetricHistorySerializer(entries, many=True).data)


class RecordMetricsView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import RiskMetricHistorySerializer

        method = request.query_params.get("method", "parametric")
        entry = RiskManagementService.record_metrics(portfolio_id, method)
        return Response(RiskMetricHistorySerializer(entry).data)


class HaltTradingView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        reason = request.data.get("reason", "")
        result = RiskManagementService.halt_trading(portfolio_id, reason)
        RiskManagementService.send_notification(
            portfolio_id, "halt", "critical", f"Trading HALTED: {reason}",
        )
        return Response(result)


class ResumeTradingView(APIView):
    def post(self, request: Request, portfolio_id: int) -> Response:
        result = RiskManagementService.resume_trading(portfolio_id)
        RiskManagementService.send_notification(
            portfolio_id, "resume", "info", "Trading RESUMED",
        )
        return Response(result)


class AlertListView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import AlertLogSerializer

        limit = int(request.query_params.get("limit", 50))
        alerts = RiskManagementService.get_alerts(portfolio_id, limit)
        return Response(AlertLogSerializer(alerts, many=True).data)


class TradeLogView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        from risk.serializers import TradeCheckLogSerializer

        limit = int(request.query_params.get("limit", 50))
        logs = RiskManagementService.get_trade_log(portfolio_id, limit)
        return Response(TradeCheckLogSerializer(logs, many=True).data)
