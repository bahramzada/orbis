from collections import defaultdict, deque
from collections.abc import Mapping
from threading import Lock
from time import perf_counter


LabelSet = tuple[tuple[str, str], ...]
DEFAULT_MAX_HISTOGRAM_SAMPLES = 1000


class MetricsRegistry:
    def __init__(
        self,
        max_histogram_samples: int = DEFAULT_MAX_HISTOGRAM_SAMPLES,
    ) -> None:
        self._lock = Lock()
        self._counters: defaultdict[tuple[str, LabelSet], float] = defaultdict(float)
        self._histograms: defaultdict[tuple[str, LabelSet], deque[float]] = defaultdict(
            lambda: deque(maxlen=max_histogram_samples)
        )

    def increment(
        self,
        name: str,
        labels: Mapping[str, str] | None = None,
        value: float = 1.0,
    ) -> None:
        key = (name, _labels(labels))
        with self._lock:
            self._counters[key] += value

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        key = (name, _labels(labels))
        with self._lock:
            self._histograms[key].append(value)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            histograms = {
                key: list(values) for key, values in self._histograms.items()
            }

        for (name, labels), value in sorted(counters.items()):
            lines.append(f"{name}{_format_labels(labels)} {value:g}")

        for (name, labels), values in sorted(histograms.items()):
            count = len(values)
            total = sum(values)
            lines.append(f"{name}_count{_format_labels(labels)} {count:g}")
            lines.append(f"{name}_sum{_format_labels(labels)} {total:g}")
            if values:
                sorted_values = sorted(values)
                p95_index = min(int(count * 0.95), count - 1)
                lines.append(
                    f"{name}_p95{_format_labels(labels)} {sorted_values[p95_index]:g}"
                )

        return "\n".join(lines) + "\n"


class Timer:
    def __init__(
        self,
        registry: MetricsRegistry,
        name: str,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        self._registry = registry
        self._name = name
        self._labels = labels
        self._started_at = perf_counter()

    def stop(self) -> float:
        elapsed = perf_counter() - self._started_at
        self._registry.observe(self._name, elapsed, self._labels)
        return elapsed


metrics = MetricsRegistry()


def timer(name: str, labels: Mapping[str, str] | None = None) -> Timer:
    return Timer(metrics, name, labels)


def _labels(labels: Mapping[str, str] | None) -> LabelSet:
    if not labels:
        return ()
    return tuple(sorted((key, _clean_label(value)) for key, value in labels.items()))


def _clean_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: LabelSet) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{rendered}}}"
