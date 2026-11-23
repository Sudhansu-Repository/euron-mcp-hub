"""Small, realistic MCP servers built on the official SDK, for the demo and the tests.

- notes (streamable HTTP): a team notebook with search, resources and prompts
- toolbox (streamable HTTP): calculator, unit and time zone conversion, a slow `wait` tool
- tickets (streamable HTTP, bearer token): a help desk, served as 1.4.0 at /mcp and as the
  older 1.3.2 at /v1/mcp, so the catalog has a real version change to show
- weather (stdio, API key in its environment): deterministic forecasts
"""
