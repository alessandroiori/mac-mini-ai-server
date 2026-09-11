"""
lightrag-mcp — minimal, self-maintained MCP server for a personal LightRAG
knowledge base. A thin proxy over LightRAG's REST API, exposing only the
tools this project actually needs (query, list, upload, note, health,
scan) — no entity/relation graph-editing tools, on purpose.

Why this exists instead of an off-the-shelf MCP wrapper: see
docs/03-lightrag-mcp-memory.md, Part 3.6 in this repo.

Required env vars:
  LIGHTRAG_BASE_URL     LightRAG's own REST endpoint, e.g. http://127.0.0.1:9621
                        (co-located with LightRAG, so plain loopback is fine)
  LIGHTRAG_API_KEY      same key as LightRAG's own .env

Optional env vars:
  MCP_TRANSPORT         "stdio" (default) or "streamable-http"
  MCP_HTTP_PORT         port for streamable-http (default 8500), bound to 127.0.0.1
                        — external exposure is `tailscale serve`'s job, not this script
  MCP_ALLOWED_HOSTS     comma-separated extra Host-header values to accept, on top of
                        127.0.0.1/localhost — needed when the server sits behind
                        `tailscale serve` or any reverse proxy, since the MCP SDK's
                        DNS-rebinding protection otherwise rejects the proxied Host
                        header (see docs/03-lightrag-mcp-memory.md, Part 3.6).
                        Example: "mymachine.tailxxxxx.ts.net:8446"
"""

import os
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

LIGHTRAG_BASE_URL = os.environ.get("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
LIGHTRAG_API_KEY = os.environ.get("LIGHTRAG_API_KEY", "")
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HTTP_PORT = int(os.environ.get("MCP_HTTP_PORT", "8500"))

if not LIGHTRAG_API_KEY:
    raise RuntimeError("LIGHTRAG_API_KEY is not set — required to talk to LightRAG")

HEADERS = {"X-API-Key": LIGHTRAG_API_KEY}

_extra_hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
_allowed_hosts = ["127.0.0.1:*", "localhost:*"] + [h if ":" in h else f"{h}:*" for h in _extra_hosts]
_allowed_origins = ["http://127.0.0.1:*"] + [f"https://{h.split(':')[0]}:*" for h in _extra_hosts]

mcp = FastMCP(
    "lightrag-knowledge-base",
    host="127.0.0.1",
    port=MCP_HTTP_PORT,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
        allowed_origins=_allowed_origins,
    ),
)


def _client() -> httpx.Client:
    return httpx.Client(base_url=LIGHTRAG_BASE_URL, headers=HEADERS, timeout=60.0)


@mcp.tool(description="Check whether the LightRAG knowledge base server is reachable and healthy.")
def check_health() -> dict:
    with _client() as c:
        r = c.get("/health")
        r.raise_for_status()
        return r.json()


@mcp.tool(
    description="List documents in the knowledge base, with processing status (processed/failed/processing)."
)
def list_documents(page: int = 1, page_size: int = 20) -> dict:
    with _client() as c:
        r = c.post("/documents/paginated", json={"page": page, "page_size": page_size})
        r.raise_for_status()
        return r.json()


@mcp.tool(description="Ingestion pipeline summary (document counts by status).")
def get_status() -> dict:
    with _client() as c:
        r = c.get("/documents/status_counts")
        r.raise_for_status()
        return r.json()


@mcp.tool(
    description=(
        "Query the knowledge base in natural language. Use mode='hybrid' or 'mix' for "
        "questions in a different language than the source documents (naive mode fails "
        "cross-lingually). Available modes: naive, local, global, hybrid, mix."
    )
)
def query_knowledge_base(query: str, mode: str = "hybrid", top_k: int = 40) -> dict:
    with _client() as c:
        r = c.post("/query", json={"query": query, "mode": mode, "top_k": top_k})
        r.raise_for_status()
        return r.json()


@mcp.tool(
    description=(
        "Upload a new document (PDF, txt, md, docx...) into the knowledge base from a file "
        "path that ALREADY EXISTS on the machine running this server. Does not transfer files "
        "from other devices — the file must already be local."
    )
)
def upload_document(file_path: str) -> dict:
    if not os.path.isfile(file_path):
        return {"status": "error", "message": f"File not found on server host: {file_path}"}
    filename = os.path.basename(file_path)
    with _client() as c:
        with open(file_path, "rb") as f:
            r = c.post("/documents/upload", files={"file": (filename, f)})
        r.raise_for_status()
        return r.json()


@mcp.tool(
    description=(
        "Add a text note directly to the knowledge base, no local file needed — useful for "
        "quick notes written in chat. 'title' becomes the source name shown in "
        "list_documents/query_knowledge_base (default: 'Note <timestamp>')."
    )
)
def insert_note(text: str, title: str = "") -> dict:
    if not title:
        title = f"Note {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    with _client() as c:
        r = c.post("/documents/text", json={"text": text, "file_source": title})
        r.raise_for_status()
        return r.json()


@mcp.tool(
    description="Trigger a rescan of LightRAG's inputs folder for files copied there manually but not yet processed."
)
def scan_for_new_documents() -> dict:
    with _client() as c:
        r = c.post("/documents/scan")
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
