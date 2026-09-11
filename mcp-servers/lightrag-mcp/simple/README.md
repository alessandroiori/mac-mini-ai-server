# lightrag-mcp (simple)

Local `stdio` version — no authentication, meant to be spawned directly by an MCP client (e.g. Claude Desktop) as a local subprocess on a machine that's already on the same network/tailnet as LightRAG.

## Configuration (environment variables)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LIGHTRAG_API_KEY` | yes | — | same key as LightRAG's own `.env` |
| `LIGHTRAG_BASE_URL` | no | `http://127.0.0.1:9621` | LightRAG's REST endpoint — use its Tailscale hostname/IP if LightRAG runs on a different machine than this server |

## Connecting from Claude Desktop

```json
{
  "mcpServers": {
    "lightrag-knowledge-base": {
      "command": "/absolute/path/to/venv/bin/python3",
      "args": ["/absolute/path/to/simple/server.py"],
      "env": {
        "LIGHTRAG_API_KEY": "<your key>",
        "LIGHTRAG_BASE_URL": "http://127.0.0.1:9621"
      }
    }
  }
}
```

If LightRAG runs on a different machine reachable over Tailscale, point `LIGHTRAG_BASE_URL` at its Tailscale HTTPS endpoint instead (see the main [`docs/03-lightrag-mcp-memory.md`](../../../docs/03-lightrag-mcp-memory.md) for how that mapping is set up) — Claude Desktop itself still runs this script locally as a `stdio` subprocess either way, no separate daemon or reverse-proxy mapping needed for the MCP layer itself.

## When to use [`remote/`](../remote) instead

If you want to reach this knowledge base from the Claude mobile app, or register it as a Custom Connector on claude.ai, `stdio` won't work — those connect to remote HTTP endpoints, not local subprocesses. Use [`remote/`](../remote) for that; see its README and [`docs/03-lightrag-mcp-memory.md`](../../../docs/03-lightrag-mcp-memory.md), Part 3.8.
