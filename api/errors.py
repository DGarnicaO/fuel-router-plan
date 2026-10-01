"""Single error schema: {"error": {"code", "message", "details"}} (DESIGN.md §7)."""

import logging

from rest_framework import exceptions, status
from rest_framework.response import Response

from geo.geocode import InvalidLocation
from planner.models import NoFeasiblePlan
from routing.base import ProviderError, ProviderTimeout, RouteNotFound

logger = logging.getLogger(__name__)


def error_response(http_status: int, code: str, message: str, details: dict | None = None):
    return Response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=http_status,
    )


def exception_handler(exc, context):
    match exc:
        case InvalidLocation():
            return error_response(
                status.HTTP_400_BAD_REQUEST, "INVALID_LOCATION", exc.message, {"value": exc.value}
            )
        case RouteNotFound():
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_LOCATION",
                "No drivable route between these locations.",
                {"provider_message": str(exc)},
            )
        case NoFeasiblePlan():
            return error_response(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "NO_FEASIBLE_PLAN",
                exc.reason,
                {
                    "from_mile": round(float(exc.from_mile), 1),
                    "to_mile": round(float(exc.to_mile), 1),
                },
            )
        case ProviderTimeout():
            return error_response(
                status.HTTP_504_GATEWAY_TIMEOUT, "PROVIDER_TIMEOUT", "Routing provider timed out."
            )
        case ProviderError():
            logger.warning("Routing provider error: %s", exc)
            return error_response(
                status.HTTP_502_BAD_GATEWAY, "PROVIDER_ERROR", "Routing provider failed."
            )
        case exceptions.Throttled():
            return error_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "THROTTLED",
                "Too many requests.",
                {"retry_after_seconds": exc.wait},
            )
        case exceptions.ValidationError():
            return error_response(
                status.HTTP_400_BAD_REQUEST, "INVALID_REQUEST", "Invalid parameters.", exc.detail
            )
        case exceptions.APIException():
            return error_response(exc.status_code, exc.default_code.upper(), str(exc.detail))
        case _:
            logger.exception("Unhandled error", exc_info=exc)
            return error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "Unexpected error."
            )
