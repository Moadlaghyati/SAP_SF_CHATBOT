class AppError(Exception):
    """Base application error."""


class DemoUserNotFoundError(AppError):
    """Raised when a demo user is not configured."""


class ConnectorUnavailableError(AppError):
    """Raised when the selected connector cannot fulfill a request."""


class LocalLLMUnavailableError(AppError):
    """Raised when the selected local LLM cannot be reached."""


class StructuredOutputError(AppError):
    """Raised when the model returns invalid structured data."""
