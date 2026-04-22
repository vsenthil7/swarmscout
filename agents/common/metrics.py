"""Shared Prometheus-metrics HTTP server helper.

Each agent/API process can call ``start_metrics_server(port)`` to expose
``/metrics`` via the ``prometheus_client`` default registry. Separated out
so it is easy to mock and easy to port to a different exposition format.
"""

from __future__ import annotations

from prometheus_client import start_http_server


def start_metrics_server(port: int) -> None:
    """Start a background HTTP server exposing ``/metrics`` on ``port``."""
    start_http_server(port)
