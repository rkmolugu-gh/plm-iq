"""Typed service errors. The API layer maps ServiceError.status_code to HTTP responses."""
from __future__ import annotations


class ServiceError(Exception):
    status_code = 400
    code = "service_error"

    def __init__(self, message: str, *, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []

    def __str__(self) -> str:
        if self.details:
            return "; ".join([self.message, *self.details])
        return self.message


class NotFound(ServiceError):  # noqa: N818
    status_code = 404
    code = "not_found"


class Conflict(ServiceError):  # noqa: N818
    status_code = 409
    code = "conflict"


class ValidationFailed(ServiceError):  # noqa: N818
    status_code = 422
    code = "validation_failed"


class Forbidden(ServiceError):  # noqa: N818
    status_code = 403
    code = "forbidden"
