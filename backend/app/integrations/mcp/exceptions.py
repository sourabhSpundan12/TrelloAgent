class MCPBaseError(Exception):
    """Base exception for all MCP related failures."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class MCPServerConnectionError(MCPBaseError):
    """Raised when an MCP server cannot be reached or connected to."""
    pass


class MCPServerNotFoundError(MCPBaseError):
    """Raised when an MCP server ID is not registered in the system."""
    pass


class MCPSSRFError(MCPBaseError):
    """Raised when an MCP server URL fails SSRF protection checks."""
    pass


class MCPToolExecutionError(MCPBaseError):
    """Raised when a remote MCP tool call fails or returns an error."""
    pass


class MCPDiscoveryError(MCPBaseError):
    """Raised when discovering tools from an MCP server fails."""
    pass

