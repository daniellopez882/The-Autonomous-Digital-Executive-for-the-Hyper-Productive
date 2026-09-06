"""
Routing latency.

Was `tests/test_performance.py`, which pytest collected as a test module even
though it contains no tests -- just a `main()` that makes live model calls. It
is a benchmark, so it lives here, outside `testpaths`.

It needs real credentials and spends real API budget. It is not run in CI, and
no number it produces appears in the README unless it was actually executed.

    python -m benchmarks.bench_routing
"""

from __future__ import annotations

import logging
import statistics
import time

from src.agents.orchestrator import MasterOrchestrator
from src.utils.config import settings

logger = logging.getLogger(__name__)

CASES = [
    ("email", "Do I have any emails today?"),
    ("calendar-create", "Schedule a meeting for tomorrow at 10am."),
    ("task-create", "Add a task to buy groceries."),
    ("calendar-read", "What is on my schedule today?"),
    ("ambiguous", "Deal with the thing from earlier."),
]

REPEATS = 3


def main() -> int:
    logging.basicConfig(level="INFO", format="%(levelname)-8s %(message)s")

    missing = settings.missing()
    if missing:
        logger.error("not configured: %s", ", ".join(missing))
        return 1

    orchestrator = MasterOrchestrator()

    # One untimed call first: the first request pays for building the model
    # client and the graph, which is not what this measures.
    orchestrator.decide_route("warm up")

    print(f"\n{'case':<18} {'route':<10} {'median s':>9} {'min':>7} {'max':>7}")
    print("-" * 56)

    for label, request in CASES:
        timings: list[float] = []
        route = None
        for _ in range(REPEATS):
            start = time.perf_counter()
            try:
                route = orchestrator.decide_route(request)
            except Exception as exc:
                print(f"{label:<18} {'FAILED':<10} {type(exc).__name__}")
                break
            timings.append(time.perf_counter() - start)
        if timings:
            print(
                f"{label:<18} {route!s:<10} {statistics.median(timings):>9.3f} "
                f"{min(timings):>7.3f} {max(timings):>7.3f}"
            )

    print(f"\n{REPEATS} runs per case, routing decision only (no tool calls).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
