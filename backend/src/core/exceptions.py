"""Domain and Application Exceptions for Trendlume"""

from fastapi.responses import JSONResponse


class TrendlumeException(Exception):
    """Base exception for all Trendlume errors"""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

    def to_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "success": False,
                "error": {
                    "code": self.code,
                    "message": self.message,
                },
            },
        )


AppException = TrendlumeException


class NotFoundException(TrendlumeException):
    """Resource not found"""

    def __init__(self, entity_name: str, entity_id: str):
        super().__init__(
            f"{entity_name} with id '{entity_id}' was not found.",
            code="NOT_FOUND",
            status_code=404,
        )
        self.entity_name = entity_name
        self.entity_id = entity_id


class ValidationException(TrendlumeException):
    """Business rule or validation error"""

    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)


class StorageException(TrendlumeException):
    """File storage operations error"""

    def __init__(self, message: str):
        super().__init__(message, code="STORAGE_ERROR", status_code=500)


class ProviderException(TrendlumeException):
    """External provider error (LLM, TTS, Media, Publishing)"""

    def __init__(self, provider_name: str, message: str):
        super().__init__(
            f"Provider '{provider_name}' error: {message}", code="PROVIDER_ERROR", status_code=502
        )
        self.provider_name = provider_name
