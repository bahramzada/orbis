from app.metrics import MetricsRegistry


def test_metrics_render_prometheus_counters_and_histograms() -> None:
    registry = MetricsRegistry()

    registry.increment("orbis_test_total", {"status": "ok"})
    registry.observe("orbis_test_duration_seconds", 0.25, {"step": "unit"})

    rendered = registry.render_prometheus()

    assert 'orbis_test_total{status="ok"} 1' in rendered
    assert 'orbis_test_duration_seconds_count{step="unit"} 1' in rendered
    assert 'orbis_test_duration_seconds_sum{step="unit"} 0.25' in rendered


def test_metrics_histogram_samples_are_bounded() -> None:
    registry = MetricsRegistry(max_histogram_samples=2)

    registry.observe("orbis_test_duration_seconds", 1.0)
    registry.observe("orbis_test_duration_seconds", 2.0)
    registry.observe("orbis_test_duration_seconds", 3.0)

    rendered = registry.render_prometheus()

    assert "orbis_test_duration_seconds_count 2" in rendered
    assert "orbis_test_duration_seconds_sum 5" in rendered
