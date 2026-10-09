"""The provider exception required by the extracted DNSE adapter."""


class ProviderUnavailableError(RuntimeError):
    """The requested symbol has no cached market data."""
