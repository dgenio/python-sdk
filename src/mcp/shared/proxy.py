"""
MCP Proxy Pattern Module

This module provides convenience functions for implementing the MCP proxy pattern,
which enables forwarding messages bidirectionally between two transports.

Example usage:
```python
async with stdio_client(server1) as client_streams, \\
           stdio_client(server2) as server_streams:
    async with mcp_proxy(
        client_streams=client_streams,
        server_streams=server_streams,
        onerror=lambda e: print(f"Proxy error: {e}"),
    ):
        # Messages are automatically forwarded between the two transports
        await anyio.sleep_forever()
```
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from mcp.shared.message import SessionMessage

logger = logging.getLogger(__name__)

# Type aliases for readability
ReadStream = MemoryObjectReceiveStream[SessionMessage | Exception]
WriteStream = MemoryObjectSendStream[SessionMessage]
MessageTransformFn = Callable[[SessionMessage], Awaitable[SessionMessage | None]]
ErrorHandlerFn = Callable[[Exception], None]


@asynccontextmanager
async def mcp_proxy(
    client_streams: tuple[ReadStream, WriteStream],
    server_streams: tuple[ReadStream, WriteStream],
    onerror: ErrorHandlerFn | None = None,
    on_client_message: MessageTransformFn | None = None,
    on_server_message: MessageTransformFn | None = None,
) -> AsyncGenerator[None, None]:
    """
    Create a bidirectional proxy between client and server transports.

    This function forwards messages between two MCP transports, enabling proxy/gateway
    use cases. Messages flow in both directions:
    - Client → Server: Messages from client are forwarded to server
    - Server → Client: Messages from server are forwarded to client

    Args:
        client_streams: Tuple of (read_stream, write_stream) for the client-facing transport
        server_streams: Tuple of (read_stream, write_stream) for the server-facing transport
        onerror: Optional callback invoked when an error occurs during forwarding.
                 The proxy continues forwarding other messages after calling this callback.
        on_client_message: Optional callback to inspect/transform messages from the client
                          before forwarding to the server. Return None to drop the message.
        on_server_message: Optional callback to inspect/transform messages from the server
                          before forwarding to the client. Return None to drop the message.

    Example:
        ```python
        async with stdio_client(server1) as client_streams, \\
                   stdio_client(server2) as server_streams:
            def log_error(error: Exception) -> None:
                logger.error(f"Proxy error: {error}")

            async def inspect_client_msg(msg: SessionMessage) -> SessionMessage | None:
                method = msg.message.root.method if hasattr(msg.message.root, "method") else "response"
                logger.info(f"Client → Server: {method}")
                return msg  # Forward as-is

            async with mcp_proxy(
                client_streams=client_streams,
                server_streams=server_streams,
                onerror=log_error,
                on_client_message=inspect_client_msg,
            ):
                # Proxy is running, forward messages until context exits
                await anyio.sleep_forever()
        ```

    Note:
        The proxy does not close the provided streams. Stream lifecycle management
        is the responsibility of the caller who owns the streams.
    """
    client_read, client_write = client_streams
    server_read, server_write = server_streams

    async def forward_messages(
        read_stream: ReadStream,
        write_stream: WriteStream,
        transform_fn: MessageTransformFn | None,
        direction: str,
    ) -> None:
        """Forward messages from read_stream to write_stream with optional transformation."""
        try:
            async for message in read_stream:
                try:
                    # Handle exceptions received from the read stream
                    if isinstance(message, Exception):
                        logger.warning(f"Received exception from {direction} stream: {message}")
                        if onerror:
                            onerror(message)
                        continue

                    # Apply transformation if provided
                    if transform_fn:
                        transformed = await transform_fn(message)
                        if transformed is None:
                            # Message was dropped by the transform function
                            logger.debug(f"Message dropped by transform function in {direction}")
                            continue
                        # Use the transformed message instead
                        await write_stream.send(transformed)
                    else:
                        # Forward the message as-is
                        await write_stream.send(message)

                except Exception as exc:
                    logger.exception(f"Error forwarding message in {direction}")
                    if onerror:
                        onerror(exc)
                    # Continue forwarding other messages

        except anyio.ClosedResourceError:
            # Stream was closed, this is expected during shutdown
            logger.debug(f"{direction} stream closed")
        except Exception as exc:
            logger.exception(f"Unexpected error in {direction} forwarding loop")
            if onerror:
                onerror(exc)

    async with anyio.create_task_group() as tg:
        # Start forwarding tasks in both directions
        tg.start_soon(
            forward_messages,
            client_read,
            server_write,
            on_client_message,
            "client→server",
        )
        tg.start_soon(
            forward_messages,
            server_read,
            client_write,
            on_server_message,
            "server→client",
        )

        try:
            yield
        finally:
            # Cancel all forwarding tasks when the context exits
            # Note: We don't close the streams here because they're owned by the caller
            # (the transport context managers that created them)
            tg.cancel_scope.cancel()
