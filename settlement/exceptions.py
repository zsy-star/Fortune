"""Settlement-specific business exceptions."""

from __future__ import annotations


class SettlementError(ValueError):
    """Base exception for settlement preview failures."""


class UnsupportedBetTypeError(SettlementError):
    """Raised when a bet type is not implemented by settlement rules."""


class InvalidSelectionError(SettlementError):
    """Raised when a supported bet type has an invalid selection."""


class InvalidDrawError(SettlementError):
    """Raised when lottery draw data is incomplete or inconsistent."""


class SettlementDataError(SettlementError):
    """Raised when order or draw data cannot be evaluated safely."""
