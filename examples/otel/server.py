"""OpenTelemetry tracing example — traces task processing end-to-end.

Run:
    pip install a2akit[otel]
    python -m examples.otel.server
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)


class MyWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Thinking...")
        await ctx.complete(f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=MyWorker(),
    agent_card=AgentCardConfig(
        name="Traced Agent",
        description="Agent with OTel tracing",
        version="0.1.0",
    ),
)
app = server.as_fastapi_app()

if __name__ == "__main__":
    import uvicorn

    print("Starting traced agent on http://localhost:8000")
    print("Traces will be printed to console.")
    print("For Jaeger: pip install opentelemetry-exporter-otlp and update the exporter.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
