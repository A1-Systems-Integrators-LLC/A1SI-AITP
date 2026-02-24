from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from portfolio.models import Holding, Portfolio
from portfolio.serializers import (
    AllocationItemSerializer,
    HoldingCreateSerializer,
    HoldingSerializer,
    HoldingUpdateSerializer,
    PortfolioCreateSerializer,
    PortfolioSerializer,
    PortfolioSummarySerializer,
    PortfolioUpdateSerializer,
)


class PortfolioListView(APIView):
    @extend_schema(responses=PortfolioSerializer(many=True), tags=["Portfolio"])
    def get(self, request: Request) -> Response:
        portfolios = Portfolio.objects.prefetch_related("holdings").all()
        return Response(PortfolioSerializer(portfolios, many=True).data)

    @extend_schema(
        request=PortfolioCreateSerializer,
        responses=PortfolioSerializer,
        tags=["Portfolio"],
    )
    def post(self, request: Request) -> Response:
        ser = PortfolioCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        portfolio = Portfolio.objects.create(**ser.validated_data)
        return Response(
            PortfolioSerializer(portfolio).data,
            status=status.HTTP_201_CREATED,
        )


class PortfolioDetailView(APIView):
    @extend_schema(responses=PortfolioSerializer, tags=["Portfolio"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PortfolioSerializer(portfolio).data)

    @extend_schema(
        request=PortfolioUpdateSerializer,
        responses=PortfolioSerializer,
        tags=["Portfolio"],
    )
    def put(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = PortfolioUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        for field, value in ser.validated_data.items():
            setattr(portfolio, field, value)
        portfolio.save()
        return Response(PortfolioSerializer(portfolio).data)

    @extend_schema(
        request=PortfolioUpdateSerializer,
        responses=PortfolioSerializer,
        tags=["Portfolio"],
    )
    def patch(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = PortfolioUpdateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        for field, value in ser.validated_data.items():
            setattr(portfolio, field, value)
        portfolio.save()
        return Response(PortfolioSerializer(portfolio).data)

    @extend_schema(tags=["Portfolio"])
    def delete(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        portfolio.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HoldingDetailView(APIView):
    @extend_schema(
        request=HoldingUpdateSerializer,
        responses=HoldingSerializer,
        tags=["Portfolio"],
    )
    def put(self, request: Request, portfolio_id: int, holding_id: int) -> Response:
        try:
            holding = Holding.objects.get(id=holding_id, portfolio_id=portfolio_id)
        except Holding.DoesNotExist:
            return Response({"error": "Holding not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = HoldingUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        for field, value in ser.validated_data.items():
            setattr(holding, field, value)
        holding.save()
        return Response(HoldingSerializer(holding).data)

    @extend_schema(tags=["Portfolio"])
    def delete(self, request: Request, portfolio_id: int, holding_id: int) -> Response:
        try:
            holding = Holding.objects.get(id=holding_id, portfolio_id=portfolio_id)
        except Holding.DoesNotExist:
            return Response({"error": "Holding not found"}, status=status.HTTP_404_NOT_FOUND)
        holding.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HoldingCreateView(APIView):
    @extend_schema(
        request=HoldingCreateSerializer,
        responses=HoldingSerializer,
        tags=["Portfolio"],
    )
    def post(self, request: Request, portfolio_id: int) -> Response:
        try:
            Portfolio.objects.get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = HoldingCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        holding = Holding.objects.create(portfolio_id=portfolio_id, **ser.validated_data)
        return Response(
            HoldingSerializer(holding).data,
            status=status.HTTP_201_CREATED,
        )


class PortfolioSummaryView(APIView):
    @extend_schema(responses=PortfolioSummarySerializer, tags=["Portfolio"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        from portfolio.services.analytics import PortfolioAnalyticsService

        try:
            summary = PortfolioAnalyticsService.get_portfolio_summary(portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PortfolioSummarySerializer(summary).data)


class PortfolioAllocationView(APIView):
    @extend_schema(responses=AllocationItemSerializer(many=True), tags=["Portfolio"])
    def get(self, request: Request, portfolio_id: int) -> Response:
        from portfolio.services.analytics import PortfolioAnalyticsService

        try:
            allocation = PortfolioAnalyticsService.get_allocation(portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AllocationItemSerializer(allocation, many=True).data)
