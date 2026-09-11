# lightrag-mcp (remote)

Standalone `streamable-http` version with a static-token auth check — safe to run as a daemon and expose publicly (e.g. via [Tailscale Funnel](https://tailscale.com/kb/1311/tailscale-funnel)), so it can be reached by the Claude mobile app or registered as a Custom Connector on claude.ai.

## Configuration (environment variables)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `LIGHTRAG_API_KEY` | yes | — | same key as LightRAG's own `.env` |
| `MCP_AUTH_TOKEN` | yes | — | static token clients must send. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `LIGHTRAG_BASE_URL` | no | `http://127.0.0.1:9621` | LightRAG's REST endpoint |
| `MCP_HTTP_PORT` | no | `8500` | bound to `127.0.0.1` — external exposure is Tailscale's job, not this script |
| `MCP_ALLOWED_HOSTS` | only if proxied | — | comma-separated Host-header values to accept besides `127.0.0.1`/`localhost` — required behind `tailscale serve`/`tailscale funnel` or any reverse proxy, otherwise the MCP SDK's DNS-rebinding protection returns `421 Invalid Host header`. Give the **bare hostname with no port** when the proxy listens on the scheme's default port (443 for HTTPS — the case for Tailscale Funnel on its default port), e.g. `mymachine.tailxxxxx.ts.net`; both that bare form and `host:<any-port>` are accepted automatically. |

Also requires `uvicorn` in the venv (`uv pip install uvicorn`) — this version serves the ASGI app directly instead of via `mcp.run()`.

## Running as a daemon + exposing over Tailscale Funnel

Same `launchd` pattern used for every other daemon in this repo (pre-create the log files before `bootstrap` — see [`docs/03-lightrag-mcp-memory.md`](../../../docs/03-lightrag-mcp-memory.md), Part 3.4, for the gotcha and the full plist).

```bash
sudo tailscale funnel --bg --https=443 <MCP_HTTP_PORT>
```

⚠️ **Tailscale Funnel only routes traffic on ports 443, 8443 and 10000 to the public internet** — the CLI accepts other ports without error, but they simply aren't reachable from outside your tailnet. Use 443 for the widest client compatibility: some infrastructure that fetches remote MCP connectors (including, empirically, claude.ai's own Custom Connector setup) appears to only reach port 443 even though Funnel also supports 8443/10000. See [`docs/03-lightrag-mcp-memory.md`](../../../docs/03-lightrag-mcp-memory.md), Part 3.8, for the full debugging story.

## Registering as a Custom Connector on claude.ai

1. Settings → Connectors → Add custom connector.
2. URL: `https://<your-tailnet-host>.ts.net/mcp` (no port needed if Funnel is on 443).
3. In "Request headers", add a header named **`x-auth-token`** with your `MCP_AUTH_TOKEN` as the value.

`Authorization` is not selectable in that UI — it's reserved for Claude's own OAuth flow, which this server doesn't implement. That's why this server checks `x-auth-token` first, falling back to `Authorization: Bearer <token>` for other MCP clients (`mcp-remote`, `curl`, etc.) that don't have that restriction.

## Connecting from Claude Desktop instead (via the `mcp-remote` bridge)

`claude_desktop_config.json` doesn't accept a bare remote `url` under `mcpServers` (see [`docs/03-lightrag-mcp-memory.md`](../../../docs/03-lightrag-mcp-memory.md), Part 3.7) — use the [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) stdio bridge, passing the token as a custom header:

```json
{
  "mcpServers": {
    "lightrag-knowledge-base": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<your-tailnet-host>.ts.net/mcp", "--transport", "http-only", "--header", "x-auth-token:${AUTH_TOKEN}"],
      "env": { "AUTH_TOKEN": "<your MCP_AUTH_TOKEN>" }
    }
  }
}
```

## When [`simple/`](../simple) is enough

If you only ever use Claude Desktop from a machine already on the same network/tailnet as LightRAG, you don't need any of the above — [`simple/`](../simple) has no auth to manage and no public exposure to think about.
