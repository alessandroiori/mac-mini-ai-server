# lightrag-mcp

A minimal, self-maintained MCP server for a personal [LightRAG](https://github.com/HKUDS/LightRAG) knowledge base.

LightRAG has no official MCP server, and the community wrappers we tried fell behind LightRAG's REST API within months of being published (see [`docs/03-lightrag-mcp-memory.md`](../../docs/03-lightrag-mcp-memory.md), Part 3.6, for the full story). This is a ~130-line proxy over the handful of REST endpoints a personal knowledge base actually needs — no graph-editing tools, easy to read end to end, easy to keep in sync with LightRAG ourselves.

Two versions, pick the one that matches how you'll use it:

| | [`simple/`](simple) | [`remote/`](remote) |
|---|---|---|
| Transport | `stdio` (local subprocess) | `streamable-http` (standalone service) |
| Authentication | none | static token, header `x-auth-token` or `Authorization: Bearer` |
| Reachable from | the machine it runs on / same network as a client that spawns it | anywhere, once exposed (e.g. Tailscale Funnel) |
| Use case | Claude Desktop on a machine already on the same network/tailnet as LightRAG | Claude mobile app, a Custom Connector on claude.ai — anything that can't reach a tailnet-private endpoint |
| Extra dependency | none beyond `mcp`/`httpx` | `uvicorn` |

Both expose the same tool set. Deliberately **not** exposed in either: entity/relation creation, editing, or merging. A personal knowledge base has no real use for graph-editing tools, and they're pure attack surface if this server is ever exposed beyond a private network. `delete_document` is the one exception to "no destructive tools" — deleting a whole document (not individual entities/relations) is common enough to be worth it, but note that on `remote/` it's gated by the same token as everything else (see the security note in [`docs/03-lightrag-mcp-memory.md`](../../docs/03-lightrag-mcp-memory.md), Part 3.8).

## Tools exposed

| Tool | Purpose |
|---|---|
| `check_health` | Is the LightRAG server up? |
| `list_documents` | Paginated list of ingested documents + status |
| `get_status` | Ingestion pipeline counts (pending/processing/processed/failed) |
| `query_knowledge_base` | Natural-language query (`naive`/`local`/`global`/`hybrid`/`mix`) — always searches the *entire* knowledge base, there is no tagging or per-document scoping (LightRAG has none built in; see note below) |
| `upload_document` | Ingest a file already present on the server's filesystem |
| `insert_note` | Ingest a text note directly, no file needed |
| `delete_document` | Permanently remove a document (and its chunks/entities/relations) by `doc_id` — no undo |
| `scan_for_new_documents` | Re-scan LightRAG's `inputs/` folder |

> **No tags, no per-query filtering.** LightRAG has no concept of labels/tags on documents, and every query mode searches the whole graph — there's no way to scope a query to "just my notes about X". The only real isolation mechanism LightRAG offers is a `workspace`, but that's set per server *instance* (a separate process/port per workspace), not something a single running server or a single query can switch between — too heavy for tagging a handful of notes. If you need hard separation between topics, running two instances (two ports, two `launchd` daemons, two MCP servers pointed at each) is the only supported way.

## Setup (either version)

```bash
uv venv venv --python 3.12
source venv/bin/activate
uv pip install "mcp<2" httpx   # mcp>=2 renamed FastMCP to MCPServer — pin <2, see docs/03
# remote/ only:
uv pip install uvicorn
deactivate
```

See [`simple/README.md`](simple/README.md) and [`remote/README.md`](remote/README.md) for the configuration and run instructions specific to each version.
