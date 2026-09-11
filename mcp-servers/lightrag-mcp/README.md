# lightrag-mcp

A minimal, self-maintained MCP server for a personal [LightRAG](https://github.com/HKUDS/LightRAG) knowledge base.

LightRAG has no official MCP server, and the community wrappers we tried fell behind LightRAG's REST API within months of being published (see [`docs/03-lightrag-mcp-memory.md`](../../docs/03-lightrag-mcp-memory.md), Part 3.6, for the full story). This is a ~130-line proxy over the handful of REST endpoints a personal knowledge base actually needs — no graph-editing tools, easy to read end to end, easy to keep in sync with LightRAG ourselves.

## Tools exposed

| Tool | Purpose |
|---|---|
| `check_health` | Is the LightRAG server up? |
| `list_documents` | Paginated list of ingested documents + status |
| `get_status` | Ingestion pipeline counts (pending/processing/processed/failed) |
| `query_knowledge_base` | Natural-language query (`naive`/`local`/`global`/`hybrid`/`mix`) |
| `upload_document` | Ingest a file already present on the server's filesystem |
| `insert_note` | Ingest a text note directly, no file needed |
| `scan_for_new_documents` | Re-scan LightRAG's `inputs/` folder |

Deliberately **not** exposed: entity/relation creation, editing, merging, or deletion. A personal knowledge base has no real use for graph-editing tools, and they're pure attack surface if this server is ever exposed beyond a private network.

## Setup

```bash
uv venv venv --python 3.12
source venv/bin/activate
uv pip install "mcp<2" httpx   # mcp>=2 renamed FastMCP to MCPServer — pin <2, see docs/03
deactivate
```

## Configuration (environment variables)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LIGHTRAG_API_KEY` | yes | — | same key as LightRAG's own `.env` |
| `LIGHTRAG_BASE_URL` | no | `http://127.0.0.1:9621` | LightRAG's REST endpoint |
| `MCP_TRANSPORT` | no | `stdio` | `stdio` for a local Claude Desktop subprocess, `streamable-http` to run as a standalone service |
| `MCP_HTTP_PORT` | no | `8500` | only used with `streamable-http` |
| `MCP_ALLOWED_HOSTS` | only if proxied | — | comma-separated `host:port` values to accept besides `127.0.0.1`/`localhost` — required if this sits behind `tailscale serve` or any reverse proxy, otherwise the MCP SDK's DNS-rebinding protection returns `421 Invalid Host header` (see docs/03, Part 3.6) |

## Running as a `launchd` daemon + exposing over Tailscale

See `docs/03-lightrag-mcp-memory.md`, Parts 3.4 and 3.6, in this repo for the full plist, log pre-creation gotcha, and `tailscale serve` mapping — same pattern used for every other daemon in this repo.

## Connecting from Claude Desktop

`claude_desktop_config.json` no longer accepts a bare remote `url` under `mcpServers`. Use the [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) stdio bridge instead:

```json
{
  "mcpServers": {
    "lightrag-knowledge-base": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<your-host>.<tailnet>.ts.net:<port>/mcp", "--transport", "http-only"]
    }
  }
}
```

See `docs/03-lightrag-mcp-memory.md`, Part 3.7, for why.
