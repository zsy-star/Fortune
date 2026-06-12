"""Scraper-specific exceptions."""


class ScraperError(RuntimeError):
    """Base scraper error."""


class ScraperTimeoutError(ScraperError):
    """Raised when a request times out."""


class ScraperForbiddenError(ScraperError):
    """Raised when the source rejects public access."""


class ScraperRateLimitedError(ScraperError):
    """Raised when the source returns 429."""


class ScraperNotFoundError(ScraperError):
    """Raised when an expected endpoint is not found."""


class ScraperServerError(ScraperError):
    """Raised when the source returns a 5xx response."""


class ScraperResponseError(ScraperError):
    """Raised when the response body cannot be parsed or has an unexpected shape."""
