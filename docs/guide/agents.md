# Routes as agent tools (MCP)

Let an AI agent use chosen routes of your app, over
[MCP](https://modelcontextprotocol.io), with each tool's capabilities declared
and a human approving the sensitive ones.

```python
# routes/orders/[order_id].py
from ushka.mcp import tool

@tool(reads=["orders"], description="Look up an order")
async def get(order_id: int):
    ...

@tool(writes=["orders"], calls=["stripe"], description="Refund an order")
async def post(order_id: int, reason: str):
    ...
```

```python
# app.py
from ushka import Ushka
from ushka.mcp import ApprovalQueue

app = Ushka()
queue = ApprovalQueue()
app.enable_mcp("/mcp", approve=queue)      # token from USHKA_MCP_TOKEN
```

Point an MCP client at `https://your-app/mcp` with `Authorization: Bearer <token>`.

## Nothing is exposed by accident

Only routes marked with `@tool` are listed. Call `enable_mcp` after your routes
exist. The tool's input schema comes from the handler's
[typed parameters](validation.md).

## Declared capabilities

| Declare | Meaning | Becomes |
| --- | --- | --- |
| `reads=["orders"]` | data it reads | `readOnlyHint`, and in the description |
| `writes=["orders"]` | data it changes | `destructiveHint`, and needs approval |
| `calls=["stripe"]` | outside services it reaches | `openWorldHint`, and needs approval |

The client shows these to the user. They are checked, too: a `GET` route that
declares `writes` is refused when you call `enable_mcp`, because a `GET` must be
safe. A tool that writes, calls out, or uses a method other than `GET` needs
approval. Override with `@tool(approval=True)` or `approval=False`.

## Human approval

Before a sensitive tool runs, your approver is asked, and it sees exactly what
will happen (`ToolCall`: the tool, method, path, arguments and capabilities).
With **no approver configured the tool is refused**.

- `ApprovalQueue`: calls wait until a person decides. Build a page or a chat
  message with `queue.pending()` and `queue.decide(id, True)`, **behind your own
  login**. No answer in `timeout` seconds (120) means no.
- `ushka.mcp.terminal_approver`: asks in the terminal that runs the server. For development.
- Your own `async def approve(call) -> bool`.

## Security

- **A token is required.** `USHKA_MCP_TOKEN` (or `token=`), compared in constant time. Without one, `enable_mcp` refuses to start, unless debug is on.
- **A tool call is a normal request to your app.** The [security middleware](security.md), validation and every `Depends` still run. A tool cannot do what its route would refuse.
- **Arguments are client data.** Strings arrive as `Untrusted`, so the guarded sinks (HTML, redirects, SQL, paths) refuse them like any request. A path argument cannot leave its segment.
- **Your routes' own authentication.** With a shared `token`, the route does *not* see the agent's `Authorization`; give it a service credential with `internal_headers={"X-Service-Key": ...}` (a dict, or a function of the request). With `token=False` the endpoint has no shared secret and passes the caller's `Authorization` to the routes, so each route authenticates its caller; use it behind a gateway.
- **Audit.** Every call is logged (`ushka.mcp`): the tool, whether it was approved, never the argument values.
- **Results are data, not instructions.** Text a tool returns goes back to the model. If it contains user-written content (a review, a ticket), it can try to steer the agent. Keep sensitive tools behind approval, and declare their `writes` honestly.
