"""Parser exception names kept at the parser package boundary."""

from app.core.exceptions import ParserDependencyError, ParserError, UnsupportedFileTypeError


__all__ = ["ParserDependencyError", "ParserError", "UnsupportedFileTypeError"]
