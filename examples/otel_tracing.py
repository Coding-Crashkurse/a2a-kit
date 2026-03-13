"""OpenTelemetry tracing example — traces task processing end-to-end.

Setup:
    pip install a2akit[otel]
    pip install opentelemetry-exporter-otlp

Run Jaeger (Docker):
    docker run -d --name jaeger \
      -p 16686:16686 -p 4317:4317 \
      jaegertracing/all-in-one:latest

Run server:
    python examples/otel_tracing.py

Send a request, then open http://localhost:16686 to see traces.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker

# --- OTel Setup (user's responsibility) ---
provider = TracerProvider()
# Use ConsoleSpanExporter for demo; replace with OTLPSpanExporter for Jaeger/Grafana
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)


# --- Normal a2akit code ---
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
