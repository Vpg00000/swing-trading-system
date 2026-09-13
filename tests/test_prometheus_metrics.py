"""
Unit tests for Prometheus Telemetry Metrics Exporter (/metrics).
Verifies exposition format version 0.0.4, headers, required gauges/counters, and metric updates.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_prometheus_metrics_format_and_headers(client):
    """Test that /metrics returns 200 OK with Prometheus exposition format text/plain; version=0.0.4."""
    response = client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type
    assert "version=0.0.4" in content_type


def test_prometheus_metrics_required_metrics_present(client):
    """
    Verify all required metrics exist in /metrics output with HELP and TYPE lines:
      - http_requests_total{method, endpoint, status}
      - http_request_duration_seconds{endpoint}
      - active_sse_connections
      - sqlite_database_bytes
      - system_memory_usage_bytes
      - system_cpu_usage_percent
    """
    # Trigger requests to generate metrics
    client.get("/api/dashboard")
    client.get("/metrics")

    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text

    # 1. http_requests_total
    assert "# HELP http_requests_total" in content
    assert "# TYPE http_requests_total counter" in content
    assert "http_requests_total{" in content
    assert 'method="GET"' in content
    assert 'status="200"' in content

    # 2. http_request_duration_seconds
    assert "# HELP http_request_duration_seconds" in content
    assert "# TYPE http_request_duration_seconds gauge" in content
    assert "http_request_duration_seconds{" in content

    # 3. active_sse_connections
    assert "# HELP active_sse_connections" in content
    assert "# TYPE active_sse_connections gauge" in content
    assert "active_sse_connections" in content

    # 4. sqlite_database_bytes
    assert "# HELP sqlite_database_bytes" in content
    assert "# TYPE sqlite_database_bytes gauge" in content
    assert "sqlite_database_bytes" in content

    # 5. system_memory_usage_bytes
    assert "# HELP system_memory_usage_bytes" in content
    assert "# TYPE system_memory_usage_bytes gauge" in content
    assert "system_memory_usage_bytes" in content

    # 6. system_cpu_usage_percent
    assert "# HELP system_cpu_usage_percent" in content
    assert "# TYPE system_cpu_usage_percent gauge" in content
    assert "system_cpu_usage_percent" in content


def test_prometheus_metrics_counters_increment(client):
    """Verify that http_requests_total counter increments when requests are made."""
    target_endpoint = "/api/execution/status"
    
    # Scrape metrics before
    resp_before = client.get("/metrics")
    content_before = resp_before.text
    
    def get_count(text, endpoint):
        for line in text.splitlines():
            if line.startswith("http_requests_total{") and f'endpoint="{endpoint}"' in line:
                try:
                    return int(line.split()[-1])
                except ValueError:
                    pass
        return 0

    count_before = get_count(content_before, target_endpoint)

    # Make 3 requests to target_endpoint
    for _ in range(3):
        res = client.get(target_endpoint)
        assert res.status_code == 200

    # Scrape metrics after
    resp_after = client.get("/metrics")
    content_after = resp_after.text
    count_after = get_count(content_after, target_endpoint)

    assert count_after == count_before + 3, f"Expected counter to increment by 3, but was before={count_before}, after={count_after}"
