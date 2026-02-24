"""Simple echo worker – returns the user's input back."""

from agentserve import A2AServer, AgentCardConfig, Worker, TaskContext, TaskResult


class EchoWorker(Worker):
    """Echoes the user's message back as-is."""

    async def handle(self, ctx: TaskContext) -> TaskResult:
        """Return the user text prefixed with 'Echo:'."""
        return TaskResult(text=f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=EchoWorker(),
    agent_card=AgentCardConfig(name="Echo", description="Echoes input", version="0.1.0"),
)
app = server.as_fastapi_app()
