"""Paramutuel MCP Server package.

Exposes the V3 protocol surface to LLM agents via the Model Context Protocol.
Read paths hit the indexer; write paths return ABI-encoded calldata so the
caller's wallet (never this server) signs and broadcasts. See
:mod:`mcp_server.server` for the tool definitions and ``docs/MACHINE.md``
for the agent-facing contract.
"""
