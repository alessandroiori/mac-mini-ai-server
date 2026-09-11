"""
lightrag-mcp (simple) — minimal MCP server for a personal LightRAG knowledge
base, meant to run as a local `stdio` subprocess of Claude Desktop (or any
other MCP client that spawns local processes). No authentication, no public
exposure — it talks to LightRAG over the network you already trust (loopback,
or a private tailnet), the same way Claude Desktop already talks to it.

Use this version if: you only ever use Claude Desktop on a machine that's
already on the same network/tailnet as LightRAG, and you don't need the
mobile app or a Custom Connector on claude.ai to reach it.

For a version that's safe to expose publicly (Tailscale Funnel + Custom
Connector on claude.ai), see ../remote/server.py instead — it adds a static
bearer-token check and runs as a standalone streamable-http service rather
than a client subprocess.

Why this exists instead of an off-the-shelf MCP wrapper for LightRAG: see
docs/03-lightrag-mcp-memory.md, Part 3.6 in this repo.

Required env vars:
  LIGHTRAG_BASE_URL     LightRAG's own REST endpoint, e.g. http://127.0.0.1:9621
  LIGHTRAG_API_KEY      same key as LightRAG's own .env
"""

import os
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

LIGHTRAG_BASE_URL = os.environ.get("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
LIGHTRAG_API_KEY = os.environ.get("LIGHTRAG_API_KEY", "")

if not LIGHTRAG_API_KEY:
    raise RuntimeError("LIGHTRAG_API_KEY is not set — required to talk to LightRAG")

HEADERS = {"X-API-Key": LIGHTRAG_API_KEY}

mcp = FastMCP("lightrag-knowledge-base")


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
    description=(
        "Permanently delete a document from the knowledge base by its doc_id (get it from "
        "list_documents). Removes the document's chunks, entities, and relations from the "
        "graph. Set delete_file=True (default) to also remove the copy LightRAG keeps of the "
        "source; this does not touch the original in ~/ai-memory/raw. There is no undo."
    )
)
def delete_document(doc_id: str, delete_file: bool = True) -> dict:
    with _client() as c:
        r = c.request(
            "DELETE",
            "/documents/delete_document",
            json={"doc_ids": [doc_id], "delete_file": delete_file, "delete_llm_cache": False},
        )
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
    mcp.run(transport="stdio")
