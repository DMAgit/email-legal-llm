"""Parser-specific exceptions."""


class ParserError(Exception):
    """Base exception for recoverable parser failures."""


class ParserDependencyError(ParserError):
    """Raised when an optional parser dependency is not installed."""


class UnsupportedFileTypeError(ParserError):
    """Raised when no parser can handle an attachment."""
