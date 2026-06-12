"""Domain-level exceptions with explicit failure reasons."""


class DomainError(ValueError):
    """Base exception for invalid business data."""


class InvalidNumberError(DomainError):
    """Raised when a lottery number is outside 01-49 or cannot be parsed."""


class UnsupportedYearError(DomainError):
    """Raised when a year-specific rule table is unavailable."""


class InvalidBetTypeError(DomainError):
    """Raised when a bet type is not supported by the domain layer."""


class InvalidRegionError(DomainError):
    """Raised when a region is not supported."""


class InvalidAmountError(DomainError):
    """Raised when an amount is zero, negative, NaN, or infinite."""


class DuplicateDrawError(DomainError):
    """Raised when a draw violates uniqueness or number distinctness rules."""
