"""Agent tracing: every agno run exported to Langfuse over OTLP.

Off unless both Langfuse keys are set, so nothing changes for a local run without them.
The OpenInference instrumentor is what makes a span carry the system prompt, chat history,
tool calls, tool results and the model response - none of that is logged by this project.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import settings

logger = logging.getLogger(__name__)

_configured = False


def configure() -> None:
    """Install the agno instrumentor once. Safe to call when tracing is disabled."""
    global _configured
    if _configured or not settings.tracing_enabled:
        return

    from openinference.instrumentation.agno import AgnoInstrumentor
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    auth = base64.b64encode(
        f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.LANGFUSE_HOST.rstrip('/')}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}"},
    )
    provider = TracerProvider(resource=Resource.create({"service.name": settings.APP_NAME}))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    AgnoInstrumentor().instrument(tracer_provider=provider)

    _configured = True
    logger.info("Agent tracing enabled - exporting to %s", settings.LANGFUSE_HOST)


@contextmanager
def case_trace(name: str, case_id) -> Iterator[None]:
    """Group the agent runs of one intake turn or workflow under a single Langfuse trace.

    `langfuse.session.id` is what puts every trace for a case on one timeline in the UI.
    """
    if not _configured:
        yield
        return
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("langfuse.session.id", str(case_id))
        yield
