import ipaddress
import socket
import urllib.parse
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from app.core.logging import logger
from app.integrations.mcp.exceptions import MCPSSRFError


def validate_url_ssrf(url: str, allow_internal: bool = False) -> None:
    """
    Validates that a URL does not target private or local networks unless allow_internal is True.
    Protects against SSRF and DNS rebinding attacks.
    """
    if not url:
        raise MCPSSRFError("URL must not be empty.")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise MCPSSRFError(f"Unsupported scheme '{parsed.scheme}'. Only http and https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise MCPSSRFError("Invalid URL: missing hostname.")

    if allow_internal:
        return

    # Check loopback hostnames
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise MCPSSRFError(
            f"Host '{hostname}' points to a local loopback address. Enable 'allow_internal' if this is an internal test server."
        )

    # Check literal IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise MCPSSRFError(f"Destination IP '{hostname}' belongs to a private or reserved network.")
    except ValueError:
        # Resolve hostname via DNS and check returned IPs
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                    raise MCPSSRFError(f"Hostname '{hostname}' resolves to private/reserved IP '{ip_str}'.")
        except socket.gaierror:
            logger.debug(f"Could not resolve hostname '{hostname}' during SSRF check; connection will fail normally.")


@asynccontextmanager
async def create_mcp_client_session(
    transport_type: str,
    url: Optional[str] = None,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 10.0,
    allow_internal: bool = False,
    custom_http_client: Optional[httpx.AsyncClient] = None,
) -> AsyncGenerator[ClientSession, None]:
    """
    Factory creating a configured MCP ClientSession with transport lifecycle management.
    Supports streamable_http, sse, and trusted local stdio.
    """
    if transport_type == "streamable_http":
        if not url:
            raise ValueError("URL is required for streamable_http transport.")
        validate_url_ssrf(url, allow_internal=allow_internal)

        if custom_http_client is not None:
            async with streamable_http_client(url, http_client=custom_http_client) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    yield session
        else:
            async with httpx.AsyncClient(timeout=timeout_seconds, headers=headers or {}) as client:
                async with streamable_http_client(url, http_client=client) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        yield session

    elif transport_type == "sse":
        if not url:
            raise ValueError("URL is required for sse transport.")
        validate_url_ssrf(url, allow_internal=allow_internal)

        async with sse_client(url, headers=headers or {}, timeout=timeout_seconds) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                yield session

    elif transport_type == "stdio":
        if not command:
            raise ValueError("Command is required for stdio transport.")
        server_params = StdioServerParameters(command=command, args=args or [])
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                yield session

    else:
        raise ValueError(f"Unsupported MCP transport_type: '{transport_type}'")

