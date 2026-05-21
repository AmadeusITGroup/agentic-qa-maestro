"""
OpenTelemetry tracing setup for Agentic QA Maestro.
"""

import logging
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)


def setup_tracing(config: Dict[str, Any]) -> Optional[TracerProvider]:
    if not config.get("enabled", True):
        logger.info("Tracing is disabled")
        return None

    service_name = config.get("service_name", "agentic-qa-maestro")
    exporter_type = config.get("exporter", "console")

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "0.1.0",
    })

    provider = TracerProvider(resource=resource)

    if exporter_type == "console":
        processor = SimpleSpanProcessor(ConsoleSpanExporter())
    elif exporter_type == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        endpoint = config.get("endpoint", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter)
    elif exporter_type == "azure_monitor":
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        connection_string = config.get("connection_string")
        if not connection_string:
            raise ValueError("Azure Monitor exporter requires 'connection_string' in config")
        exporter = AzureMonitorTraceExporter(connection_string=connection_string)
        processor = BatchSpanProcessor(exporter)
    else:
        logger.warning(f"Unknown exporter type '{exporter_type}', falling back to console")
        processor = SimpleSpanProcessor(ConsoleSpanExporter())

    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    logger.info(f"Tracing configured: service={service_name}, exporter={exporter_type}")
    return provider


def get_tracer(name: str = "agentic_qa_maestro") -> trace.Tracer:
    return trace.get_tracer(name)


def setup_logging(config: Dict[str, Any]) -> None:
    level_name = config.get("level", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("agent_framework").setLevel(logging.INFO)
