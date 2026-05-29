from app.metrics import MetricsRegistry


def test_metrics_render_prometheus_counters_and_histograms() -> None:
    registry = MetricsRegistry()

    registry.increment("orbis_test_total", {"status": "ok"})
    registry.observe("orbis_test_duration_seconds", 0.25, {"step": "unit"})

    rendered = registry.render_prometheus()

    assert 'orbis_test_total{status="ok"} 1' in rendered
    assert 'orbis_test_duration_seconds_count{step="unit"} 1' in rendered
    assert 'orbis_test_duration_seconds_sum{step="unit"} 0.25' in rendered
