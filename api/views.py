from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from api.serializers import RoutePlanQuerySerializer, serialize_plan
from api.services import PlanParams, RoutePlanService
from routing.providers import get_route_provider


class RoutePlanThrottle(AnonRateThrottle):
    """Protects the routing quota. Rate is read at request time so it lives in FUEL_PLANNER."""

    scope = "route_plan"

    def get_rate(self) -> str:
        return settings.FUEL_PLANNER["THROTTLE_RATE"]


class RoutePlanView(APIView):
    throttle_classes = [RoutePlanThrottle]

    def get(self, request: Request) -> Response:
        query = RoutePlanQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        result = RoutePlanService(get_route_provider()).plan(PlanParams(**query.validated_data))
        response = Response(serialize_plan(result))
        response["Server-Timing"] = ", ".join(
            f"{name};dur={ms:.1f}" for name, ms in result.timings_ms.items()
        )
        return response
