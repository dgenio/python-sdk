# Simple MCP Proxy Server

A simple MCP proxy server that demonstrates the `mcp_proxy()` pattern by forwarding messages bidirectionally between an MCP client and an MCP server.

## Features

- **Transparent proxying**: Forwards all MCP messages between client and server
- **Message inspection**: Optional logging of messages flowing through the proxy
- **Error handling**: Robust error handling with logging
- **Easy configuration**: Simple command-line interface

## Use Cases

This proxy pattern is useful for:

- **Debugging**: Inspect MCP protocol messages between client and server
- **Monitoring**: Log and track MCP interactions
- **Gateway**: Add authentication, rate limiting, or other middleware
- **Testing**: Simulate network conditions or inject test messages

## Usage

Start the proxy server by pointing it to a backend MCP server:

```bash
# Proxy to the simple-tool server with message inspection
uv run mcp-simple-proxy --server-command uv --server-args run --server-args mcp-simple-tool

# Proxy without message inspection
uv run mcp-simple-proxy --server-command uv --server-args run --server-args mcp-simple-tool --no-inspect

# Proxy to any other MCP server
uv run mcp-simple-proxy --server-command python --server-args my_server.py
```

The proxy listens on stdin/stdout (like a normal MCP server), so you can connect to it with any MCP client.

## Example Client Usage

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    # Connect to the proxy (which forwards to the backend server)
    async with stdio_client(
        StdioServerParameters(
            command="uv",
            args=["run", "mcp-simple-proxy", 
                  "--server-command", "uv",
                  "--server-args", "run",
                  "--server-args", "mcp-simple-tool"]
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools (proxied from backend server)
            tools = await session.list_tools()
            print(f"Available tools: {tools}")

            # Call a tool (proxied to backend server)
            result = await session.call_tool("fetch", {"url": "https://example.com"})
            print(f"Result: {result}")


asyncio.run(main())
```

## Message Inspection Output

When inspection is enabled, the proxy logs messages flowing through it:

```text
INFO:__main__:Starting MCP proxy to: uv run mcp-simple-tool
INFO:__main__:Proxy connections established
INFO:__main__:Proxy is running. Press Ctrl+C to stop.
INFO:__main__:Client → Server: initialize (id: 1)
INFO:__main__:Server → Client: Response (id: 1)
INFO:__main__:Client → Server: initialized (id: N/A)
INFO:__main__:Client → Server: tools/list (id: 2)
INFO:__main__:Server → Client: Response (id: 2)
INFO:__main__:Client → Server: tools/call (id: 3)
INFO:__main__:Server → Client: Response (id: 3)
```

## Advanced Usage

You can extend this example to add custom functionality:

```python
from mcp.shared.proxy import mcp_proxy

async def transform_message(msg: SessionMessage) -> SessionMessage | None:
    # Add authentication headers
    # Rate limit requests
    # Cache responses
    # Drop certain messages
    return msg

async with mcp_proxy(
    client_streams=client_streams,
    server_streams=server_streams,
    on_client_message=transform_message,
):
    await anyio.sleep_forever()
```

## Architecture

```text
┌─────────┐         ┌───────────────┐         ┌─────────┐
│  MCP    │◄───────►│  MCP Proxy    │◄───────►│  MCP    │
│ Client  │  stdio  │   (this)      │  stdio  │ Server  │
└─────────┘         └───────────────┘         └─────────┘
                          ↓
                    Message inspection,
                    transformation, etc.
```

The proxy creates two transport connections:

- **Client-facing**: Communicates with the MCP client via stdin/stdout
- **Server-facing**: Communicates with the backend MCP server via stdio_client

All messages are forwarded bidirectionally through the `mcp_proxy()` function.
