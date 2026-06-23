from typing import Any, Optional, Dict


class AppError(Exception):
    """
    Base application error (AI-friendly + API-friendly)
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# =========================
# 🔥 COMMON PREDEFINED ERRORS
# =========================


class OdooConnectionError(AppError):
    def __init__(self, message="Failed to connect to Odoo", details=None):
        super().__init__(
            code="ODOO_CONNECTION_FAILED",
            message=message,
            details=details,
            status_code=502,
        )


class OdooTimeoutError(AppError):
    def __init__(self, message="Odoo request timeout", details=None):
        super().__init__(
            code="ODOO_TIMEOUT",
            message=message,
            details=details,
            status_code=504,
        )


class OdooRPCError(AppError):
    def __init__(self, message="Odoo RPC error", details=None):
        super().__init__(
            code="ODOO_RPC_ERROR",
            message=message,
            details=details,
            status_code=500,
        )


class ValidationError(AppError):
    def __init__(self, message="Validation error", details=None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            status_code=422,
        )


class NotFoundError(AppError):
    def __init__(self, message="Resource not found", details=None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            details=details,
            status_code=404,
        )
