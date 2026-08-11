"""Typed failures used by China-market data providers."""


class ProviderError(RuntimeError):
    """Base error for a provider failure that the router can classify."""


class RateLimitError(ProviderError):
    """The provider rejected a request because of a frequency limit."""


class AuthenticationError(ProviderError):
    """The configured provider credential is missing or invalid."""


class PermissionError(ProviderError):
    """The credential is valid but lacks access to the requested endpoint."""


class EmptyDataError(ProviderError):
    """The request succeeded but returned no usable data."""


class UnsupportedSymbolError(ProviderError):
    """The provider cannot serve the requested canonical A-share symbol."""


class TimeoutError(ProviderError):
    """The provider did not respond within the allowed time."""


class SchemaChangedError(ProviderError):
    """The upstream response no longer satisfies the expected field contract."""
