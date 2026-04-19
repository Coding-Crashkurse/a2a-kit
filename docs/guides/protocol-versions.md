# Protocol Versions

a2akit speaks **A2A v1.0** natively. Each `A2AServer` serves **exactly one** A2A wire version — either v1.0 (default) or v0.3. There is no dual-serving mode. If you need to bridge a mixed fleet, run two `A2AServer` instances on different ports.

## Picking a version

The `A2AServer(protocol_version=...)` kwarg controls the wire format.

```python
from a2akit import A2AServer, AgentCardConfig

# Default: v1.0 (current spec)
A2AServer(worker=..., agent_card=AgentCardConfig(...))

# Legacy: v0.3 (pre-1.0 clients)
A2AServer(worker=..., agent_card=..., protocol_version="0.3")
```

You can also set the process-wide default via environment variable:

```bash
export A2AKIT_DEFAULT_PROTOCOL_VERSION=0.3
```

Passing a set or list to `protocol_version` (e.g. `{"1.0", "0.3"}`) raises `ValueError` at `A2AServer.__init__`. Single-version is a deliberate design choice: dual-serving would require two wire stacks on one app, a JSON-RPC dispatcher that routes by method shape, and twin middleware pipelines — complexity that's rarely worth it in practice.

The `A2AClient` is version-neutral — it auto-detects the server's protocol from the agent card, reading `supportedInterfaces[]` on v1.0 cards and falling back to `preferredTransport` + `additionalInterfaces[]` on v0.3 cards.

## Version mismatch between client and server

When a client can't speak what the server serves, you get a typed error.

### Where mismatches are detected

| Situation | Where it's caught | Exception raised |
|---|---|---|
| Server card advertises a version the client doesn't support (e.g. "2.0" only) | client `connect()` pre-flight | `ProtocolVersionMismatchError` |
| Client sends `A2A-Version: 0.3.0` to a v1.0 server | server `_check_a2a_version_v10` → HTTP 400 | transport maps to `ProtocolVersionMismatchError` |
| Client sends `A2A-Version: 1.0` to a v0.3 server | server `_check_a2a_version` → HTTP 400, JSON-RPC code `-32009` | transport maps to `ProtocolVersionMismatchError` |
| Misconfigured server (card says v1.0 but endpoint is v0.3) | first request round-trips to an unknown path | `TaskNotFoundError` / `ProtocolError` (framework-level) |

### Catching it

```python
from a2akit import A2AClient
from a2akit.client.errors import ProtocolVersionMismatchError

try:
    async with A2AClient("http://remote-agent:8000") as client:
        result = await client.send("hello")
except ProtocolVersionMismatchError as exc:
    # exc.client_version  — what the client tried ("0.3.0" / "1.0")
    # exc.server_version  — what the server advertises / accepts
    # exc.detail          — raw message from the server
    print(f"Cannot talk to this agent: {exc}")
```

## What v1.0 changes on the wire

| Aspect | v0.3 | v1.0 |
|---|---|---|
| REST paths | `/v1/message:send`, `/v1/tasks/{id}` | `/message:send`, `/tasks/{id}` (no prefix) |
| JSON-RPC methods | `message/send`, `tasks/get` | `SendMessage`, `GetTask` (PascalCase) |
| `Part` shape | `{"kind": "text", "text": "..."}` discriminator | Flat: `{"text": "..."}`, `{"url": "...", "media_type": "..."}` |
| `Role` enum | `"user"` / `"agent"` | `"ROLE_USER"` / `"ROLE_AGENT"` |
| `TaskState` enum | `"submitted"` / `"completed"` | `"TASK_STATE_SUBMITTED"` / `"TASK_STATE_COMPLETED"` |
| Error envelope | `{"code": -32001, "message": "..."}` | `google.rpc.Status` with `ErrorInfo.reason` (`TASK_NOT_FOUND`, …) |
| Streaming SSE | Bare `Task`/`Status`/`Artifact` events, `final: true` flag | Wrapped: `{"taskStatusUpdate": {...}}`, `{"taskArtifactUpdate": {...}, "index": N}`; stream close = terminal |
| Push config | Nested `{taskId, pushNotificationConfig: {url, token, ...}}` | Flat `{taskId, id, url, token, authentication}` |
| Agent card | `preferredTransport` + `additionalInterfaces[]` | `supportedInterfaces[]` with per-entry `protocolVersion` + `protocolBinding` |
| Card signing | Not specified | Detached JWS (RFC 7515) + JCS canonicalization (RFC 8785) |

## Signature verification on the client

The client verifies JWS signatures on agent cards (spec §19) by default in `"soft"` mode — it validates any signatures present and warns if missing. Flip to `"strict"` to require verifiable signatures, or `"off"` to skip entirely.

```python
from a2akit import A2AClient

async with A2AClient(
    "http://remote-agent:8000",
    verify_signatures="strict",
    trusted_signing_keys=[my_public_jwk],
) as client:
    ...
```

Requires the `signatures` extra: `pip install a2akit[signatures]`.

## Picking between v1.0 and v0.3

Use **v1.0** unless you have a specific reason not to. It's the current spec and the easier surface to reason about.

Use **v0.3** only if you're serving known legacy clients that haven't upgraded.

If you have a mixed fleet at rollout time, run two servers on different ports and put a reverse proxy in front that routes by URL prefix. Don't try to reimplement dual-serving on top of a2akit — if you need it, the architectural pain is better kept in the proxy layer.
