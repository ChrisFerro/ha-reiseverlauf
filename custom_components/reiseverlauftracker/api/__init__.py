"""
API package for reiseverlauftracker.

Exception hierarchy:
    ReiseverlaufApiClientError (base)
    ├── ReiseverlaufApiClientCommunicationError (network/timeout)
    └── ReiseverlaufApiClientAuthenticationError (401/403)

The coordinator maps them onto ConfigEntryAuthFailed and UpdateFailed; nothing else
in the integration imports this package.
"""

from .client import (
    FAN_SPEEDS,
    ReiseverlaufApiClient,
    ReiseverlaufApiClientAuthenticationError,
    ReiseverlaufApiClientCommunicationError,
    ReiseverlaufApiClientError,
)

__all__ = [
    "FAN_SPEEDS",
    "ReiseverlaufApiClient",
    "ReiseverlaufApiClientAuthenticationError",
    "ReiseverlaufApiClientCommunicationError",
    "ReiseverlaufApiClientError",
]
