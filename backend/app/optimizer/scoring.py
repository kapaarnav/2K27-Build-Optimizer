"""Fit score for a verified recipe.

The displayed score reads how close a recipe is to the request. It is not an
NBA 2K meta grade. Rank order is separate: required misses, then prioritized
misses, then normal misses, then a physical-preference tie-break, then fewer
Cap Breakers. Playstyle is recorded and does not change that order.
"""

from dataclasses import dataclass

DISPLAY_PRIORITIZED_RATING = 10
DISPLAY_PRIORITIZED_UNLOCK = 10
DISPLAY_NORMAL_RATING = 2
DISPLAY_NORMAL_UNLOCK = 1

# Product threshold for the distinct-alternative list. Not a game-rule number.
ALTERNATIVE_SCORE_BAND = 20


def fit_score(
    *,
    prioritized_points: int,
    normal_points: int,
    prioritized_unlock_misses: int,
    normal_unlock_misses: int,
    required_points: int = 0,
    required_unlock_misses: int = 0,
) -> float:
    penalty = (
        required_points * DISPLAY_PRIORITIZED_RATING
        + required_unlock_misses * DISPLAY_PRIORITIZED_UNLOCK
        + prioritized_points * DISPLAY_PRIORITIZED_RATING
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


def violation_weight(weights: ObjectiveWeights, *, n_attributes: int, n_unlocks: int) -> int:
    """One required miss outranks every softer penalty."""

    span = 150 * max(n_attributes, 1) + max(n_unlocks, 1)
    return weights.prioritized * span + 1
