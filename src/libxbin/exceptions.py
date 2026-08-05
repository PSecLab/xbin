class XbinError(Exception):
    """Base exception for all libxbin errors."""
    pass

class XbinConnectionError(XbinError):
    """Raised when unable to connect to the xbin orchestrator."""
    pass

class AnalysisTimeoutError(XbinError):
    """Raised when waiting for analysis results exceeds the specified timeout."""
    pass

class PluginError(XbinError):
    """Raised when a plugin action (start/stop/log) fails."""
    pass

class APIError(XbinError):
    """Raised when the xbin REST API returns an unexpected HTTP status code or payload."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
