"""Record latency for the toy multi-body search.

This is not a pass/fail gate. Run it when tuning the request deadline.
The numbers describe the synthetic fixture, not an NBA 2K27 search.
"""

import statistics
import time
from pathlib import Path

from app.optimizer.portfolio import search_bodies
from app.optimizer.solve import SolveBudget
from app.rules.loader import load_ruleset
from app.schemas.optimize import OptimizeRequest

_GUARD = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synthetic" / "guard"
_RUNS = 20


def _request(playstyle: str) -> OptimizeRequest:
    return OptimizeRequest.model_validate(
        {
            "playstyle": playstyle,
            "body": {
                "build_type": {"value": "male", "locked": True},
                "position": {"value": "PG", "locked": True},
                "height_in": {"value": 74, "locked": False},
                "weight_lb": {"value": None, "locked": False},
                "wingspan_in": {"value": None, "locked": False},
            },
            "attribute_targets": [
                {"id": "toy_shot", "target": 80, "importance": "prioritized"},
                {"id": "toy_finish", "target": 40, "importance": "required"},
            ],
        }
    )


def main() -> None:
    ruleset = load_ruleset(_GUARD, allow_synthetic=True)
    samples: list[float] = []
    for _ in range(_RUNS):
        started = time.perf_counter()
        outcome = search_bodies(ruleset.bundle, _request("balanced"), SolveBudget())
        samples.append((time.perf_counter() - started) * 1000)
        if outcome.status != "complete_proven":
            raise SystemExit(f"Benchmark expected a proven toy search, got {outcome.status}.")
    ordered = sorted(samples)

    def percentile(rank: float) -> float:
        index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * rank)))
        return ordered[index]

    print(f"runs {_RUNS}")
    print(f"p50_ms {percentile(0.50):.2f}")
    print(f"p95_ms {percentile(0.95):.2f}")
    print(f"mean_ms {statistics.fmean(samples):.2f}")


if __name__ == "__main__":
    main()
