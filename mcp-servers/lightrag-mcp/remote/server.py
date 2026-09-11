"""
lightrag-mcp (remote) — MCP server for a personal LightRAG knowledge base,
built to run as a standalone streamable-http service that's safe to expose
publicly (e.g. via Tailscale Funnel) and register as a Custom Connector on
claude.ai — the only way to reach it from the Claude mobile app, which talks
to remote connectors through Anthropic's own infrastructure rather than
reaching a tailnet-private endpoint directly.

Use this version if: you want the knowledge base reachable from outside your
tailnet (mobile app, a Custom Connector on claude.ai). For same-network-only
use with Claude Desktop, ../simple/server.py is simpler (no auth to manage).

Authentication: the official MCP SDK's built-in auth mechanism
(token_verifier/AuthSettings) is designed for a real OAuth authorization
server (it requires an issuer_url) — overkill for a single-user personal
server with one static token. Instead we wrap the raw ASGI app returned by
mcp.streamable_http_app() with a small Starlette middleware that checks a
static token before letting any request through. It accepts the token via
either of two headers:
  - "x-auth-token: <token>" — the header claude.ai's Custom Connector setup
    lets you add (it reserves "Authorization" for its own OAuth flow, so a
    plain bearer token can't go there).
  - "Authorization: Bearer <token>" — for generic MCP clients (mcp-remote,
    curl, etc.) that don't have that restriction.

Why a custom server at all instead of an off-the-shelf MCP wrapper for
LightRAG: see docs/03-lightrag-mcp-memory.md, Part 3.6 in this repo.

Required env vars:
  LIGHTRAG_BASE_URL     LightRAG's own REST endpoint, e.g. http://127.0.0.1:9621
                        (co-located with LightRAG, so plain loopback is fine)
  LIGHTRAG_API_KEY      same key as LightRAG's own .env
  MCP_AUTH_TOKEN        static token clients must send (see above). Generate
                        one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"

Optional env vars:
  MCP_HTTP_PORT         port to bind (default 8500), bound to 127.0.0.1 —
                        external exposure is Tailscale's job, not this script
  MCP_ALLOWED_HOSTS     comma-separated Host-header values to accept, on top of
                        127.0.0.1/localhost — needed behind any reverse proxy
                        (tailscale serve/funnel included), since the MCP SDK's
                        DNS-rebinding protection otherwise rejects the proxied
                        Host header (see docs/03-lightrag-mcp-memory.md, Part
                        3.6). Give the bare hostname with no port when the
                        proxy listens on the scheme's default port (443 for
                        HTTPS, as with Tailscale Funnel on its default port) —
                        e.g. "mymachine.tailxxxxx.ts.net" — both the bare host
                        and "host:<any-port>" are accepted automatically.
"""

import os
import secrets
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

LIGHTRAG_BASE_URL = os.environ.get("LIGHTRAG_BASE_URL", "http://127.0.0.1:9621")
LIGHTRAG_API_KEY = os.environ.get("LIGHTRAG_API_KEY", "")
MCP_HTTP_PORT = int(os.environ.get("MCP_HTTP_PORT", "8500"))
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

if not LIGHTRAG_API_KEY:
    raise RuntimeError("LIGHTRAG_API_KEY is not set — required to talk to LightRAG")

if not MCP_AUTH_TOKEN:
    raise RuntimeError(
        "MCP_AUTH_TOKEN is not set — required for this server, otherwise anyone "
        "who can reach the port can use it with no authentication at all."
    )

HEADERS = {"X-API-Key": LIGHTRAG_API_KEY}

_extra_hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
_allowed_hosts = ["127.0.0.1:*", "localhost:*"]
for _h in _extra_hosts:
    if ":" in _h:
        _allowed_hosts.append(_h)
    else:
        # Accept both "host:<any-port>" and the bare host with no port at all —
        # the Host header omits the port when it's the default for the scheme
        # (443 for HTTPS), e.g. behind Tailscale Funnel on its default port.
        _allowed_hosts.append(f"{_h}:*")
        _allowed_hosts.append(_h)
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


def _build_authenticated_app():
    """Wraps mcp.streamable_http_app() with a static-token check.

    The MCP SDK has no simple way to check a single static token (its
    built-in auth mechanism targets OAuth with an issuer_url), so we do it by
    hand with a Starlette middleware layered on top of the raw ASGI app.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class TokenAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            provided = request.headers.get("x-auth-token", "").strip()
            if not provided:
                auth_header = request.headers.get("authorization", "")
                if auth_header.lower().startswith("bearer "):
                    provided = auth_header[7:].strip()
            if not provided or not secrets.compare_digest(provided, MCP_AUTH_TOKEN):
                return JSONResponse(
                    {"error": "unauthorized", "message": "Missing or invalid token."},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)

    app = mcp.streamable_http_app()
    app.add_middleware(TokenAuthMiddleware)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(_build_authenticated_app(), host="127.0.0.1", port=MCP_HTTP_PORT)
