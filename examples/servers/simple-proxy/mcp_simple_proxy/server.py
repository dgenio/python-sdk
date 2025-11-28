"""
Simple MCP Proxy Server Example

This example demonstrates how to use the mcp_proxy() function to create a proxy
that forwards messages between a client and a server, with optional message inspection.
"""

import logging
import sys

import anyio
import click
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage
from mcp.shared.proxy import mcp_proxy

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


async def inspect_client_message(msg: SessionMessage) -> SessionMessage | None:
    """Inspect messages from the client before forwarding to the server."""
    root = msg.message.root
    if hasattr(root, "method"):
        logger.info(f"Client → Server: {root.method} (id: {getattr(root, 'id', 'N/A')})")
    elif hasattr(root, "result"):
        logger.info(f"Client → Server: Response (id: {getattr(root, 'id', 'N/A')})")
    elif hasattr(root, "error"):
        logger.info(f"Client → Server: Error (id: {getattr(root, 'id', 'N/A')})")
    return msg


async def inspect_server_message(msg: SessionMessage) -> SessionMessage | None:
    """Inspect messages from the server before forwarding to the client."""
    root = msg.message.root
    if hasattr(root, "method"):
        logger.info(f"Server → Client: {root.method} (id: {getattr(root, 'id', 'N/A')})")
    elif hasattr(root, "result"):
        logger.info(f"Server → Client: Response (id: {getattr(root, 'id', 'N/A')})")
    elif hasattr(root, "error"):
        logger.info(f"Server → Client: Error (id: {getattr(root, 'id', 'N/A')})")
    return msg


def handle_error(error: Exception) -> None:
    """Handle errors that occur during proxying."""
    logger.error(f"Proxy error: {error}", exc_info=True)


@click.command()
@click.option("--server-command", required=True, help="Command to start the MCP server")
@click.option("--server-args", multiple=True, help="Arguments for the server command")
@click.option("--inspect/--no-inspect", default=True, help="Enable message inspection logging")
def main(server_command: str, server_args: tuple[str, ...], inspect: bool) -> int:
    """
    MCP Proxy Server

    This server acts as a proxy between an MCP client and an MCP server,
    forwarding messages bidirectionally while optionally logging/inspecting them.

    Example usage:
        # Proxy to the simple-tool server with inspection
        mcp-simple-proxy --server-command uv --server-args run --server-args mcp-simple-tool

        # Proxy without inspection
        mcp-simple-proxy --server-command uv --server-args run --server-args mcp-simple-tool --no-inspect
    """
    logger.info(f"Starting MCP proxy to: {server_command} {' '.join(server_args)}")

    async def run_proxy():
        # Set up connection to the backend server
        server_params = StdioServerParameters(
            command=server_command,
            args=list(server_args),
        )

        # Connect to the backend server and set up stdio for client
        async with (
            stdio_client(server_params, errlog=sys.stderr) as server_streams,
            stdio_server() as client_streams,
        ):
            logger.info("Proxy connections established")

            # Run the proxy with optional inspection
            async with mcp_proxy(
                client_streams=client_streams,
                server_streams=server_streams,
                onerror=handle_error,
                on_client_message=inspect_client_message if inspect else None,
                on_server_message=inspect_server_message if inspect else None,
            ):
                logger.info("Proxy is running. Press Ctrl+C to stop.")
                # Keep the proxy running until interrupted
                await anyio.sleep_forever()

    try:
        anyio.run(run_proxy)
    except KeyboardInterrupt:
        logger.info("Proxy stopped by user")
    except Exception as e:
        logger.error(f"Proxy failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
