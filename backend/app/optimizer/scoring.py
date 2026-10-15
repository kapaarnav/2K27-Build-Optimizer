"""Fit score for one locked body.

The displayed score reads how close a recipe is to the request. It is not an
NBA 2K meta grade. The solver uses a separate hierarchical weight: a
prioritized miss outranks every normal miss, and a normal miss outranks
breaker placement.
"""

from dataclasses import dataclass

DISPLAY_PRIORITIZED_RATING = 10
DISPLAY_PRIORITIZED_UNLOCK = 10
DISPLAY_NORMAL_RATING = 2
DISPLAY_NORMAL_UNLOCK = 1


def fit_score(
    *,
    prioritized_points: int,
    normal_points: int,
    prioritized_unlock_misses: int,
    normal_unlock_misses: int,
) -> float:
    penalty = (
        prioritized_points * DISPLAY_PRIORITIZED_RATING
        + prioritized_unlock_misses * DISPLAY_PRIORITIZED_UNLOCK
        + normal_points * DISPLAY_NORMAL_RATING
        + normal_unlock_misses * DISPLAY_NORMAL_UNLOCK
    )
    return float(max(0, 100 - min(100, penalty)))


@dataclass(frozen=True)
class ObjectiveWeights:
    prioritized: int
    normal: int
    unlock_normal: int
    stability: int
    breaker_base: int


def objective_weights(
    *,
    n_attributes: int,
    n_pools: int,
    total_applications: int,
    n_unlocks: int,
) -> ObjectiveWeights:
    """Weights that keep the hierarchy inside a 64-bit objective."""

    attributes = max(n_attributes, 1)
    pools = max(n_pools, 1)
    applications = max(total_applications, 1)
    # One application on the last pool stays cheaper than two on the first.
    breaker_base = pools
    max_breaker = applications * (breaker_base + pools)
    stability = max_breaker + 1
    max_stability = stability * (150 * attributes + applications)
    normal = max_stability + 1
    max_normal = normal * (150 * attributes + max(n_unlocks, 1))
    prioritized = max_normal + 1
    return ObjectiveWeights(
        prioritized=prioritized,
        normal=normal,
        unlock_normal=stability,
        stability=stability,
        breaker_base=breaker_base,
    )
