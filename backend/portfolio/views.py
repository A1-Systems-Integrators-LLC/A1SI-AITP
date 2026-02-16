from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from portfolio.models import Holding, Portfolio
from portfolio.serializers import (
    HoldingCreateSerializer,
    HoldingSerializer,
    PortfolioCreateSerializer,
    PortfolioSerializer,
)


class PortfolioListView(APIView):
    def get(self, request: Request) -> Response:
        portfolios = Portfolio.objects.prefetch_related("holdings").all()
        return Response(PortfolioSerializer(portfolios, many=True).data)

    def post(self, request: Request) -> Response:
        ser = PortfolioCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        portfolio = Portfolio.objects.create(**ser.validated_data)
        return Response(
            PortfolioSerializer(portfolio).data,
            status=status.HTTP_201_CREATED,
        )


class PortfolioDetailView(APIView):
    def get(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.prefetch_related("holdings").get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PortfolioSerializer(portfolio).data)

    def delete(self, request: Request, portfolio_id: int) -> Response:
        try:
            portfolio = Portfolio.objects.get(id=portfolio_id)
        except Portfolio.DoesNotExist:
            return Response({"error": "Portfolio not found"}, status=status.HTTP_404_NOT_FOUND)
        portfolio.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HoldingCreateView(APIView):
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
