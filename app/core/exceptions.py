"""Shared exception taxonomy for predictable application failures."""


class ApplicationError(Exception):
    """Base class for expected application-level failures."""


class ConfigurationError(ApplicationError):
    """Raised when local configuration prevents an operation from running."""


class ModelConfigError(ConfigurationError):
    """Raised when YAML model configuration is missing or malformed."""


class ParserError(ApplicationError):
    """Base class for recoverable parser failures."""


class UnsupportedFileTypeError(ParserError):
    """Raised when no parser can handle an attachment."""


class ParserDependencyError(ParserError):
    """Raised when an optional parser dependency is not installed."""


class ExternalServiceError(ApplicationError):
    """Raised when an external service call fails or returns unusable data."""


class PersistenceError(ApplicationError):
    """Raised when persistence cannot store or retrieve expected state."""


class IngestionError(ApplicationError):
    """Raised when an inbound webhook payload cannot be normalized."""


class ExtractionError(ApplicationError):
    """Raised when a parsed document cannot be converted into structured fields."""


class RetrievalError(ApplicationError):
    """Raised when policy context cannot be retrieved for classification."""


class ClassificationError(ApplicationError):
    """Raised when extracted fields cannot be classified into a risk result."""


class OpenAIClientError(ExternalServiceError):
    """Raised when OpenAI cannot produce a usable structured response."""


class OpenAIClientConfigurationError(OpenAIClientError, ConfigurationError):
    """Raised when the OpenAI client cannot be initialized."""


class SearchClientError(ExternalServiceError):
    """Raised when Azure AI Search cannot produce usable retrieval results."""


class SearchClientConfigurationError(SearchClientError, ConfigurationError):
    """Raised when the Azure AI Search client cannot be initialized."""


class SearchIndexNotFoundError(SearchClientError):
    """Raised when the configured Azure AI Search index is missing."""
