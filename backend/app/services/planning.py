from dataclasses import dataclass

from app.domain import MECHANIC_FIELDS, OPTIMIZER_VERSION, SCORING_VERSION
from app.rules.loader import ActiveRuleset
from app.schemas.optimize import (
    CacheInfo,
    CoverageReport,
    FieldIssue,
    OptimizeRequest,
    RecommendationSet,
    UnsupportedOptimizeResponse,
    ValidateResponse,
)


@dataclass(frozen=True)
class CoverageDecision:
    supported: bool
    notes: list[str]
    missing_mechanics: list[str]

    def as_report(self) -> CoverageReport:
        return CoverageReport(
            supported=self.supported,
            notes=list(self.notes),
            missing_mechanics=list(self.missing_mechanics),
        )


def assess_coverage(ruleset: ActiveRuleset, request: OptimizeRequest) -> CoverageDecision:
    """Decide whether verified rules can honor this request.

    A locked position must itself be fully verified. An unlocked measurement is
    only a preference, so any fully verified position keeps the request covered.
    Missing coverage is unsupported, never infeasible.
    """

    verified = ruleset.manifest.fully_verified_positions()
    if request.body.position.locked:
        position = request.body.position.value
        if position is None:
            raise RuntimeError("A locked position is missing its value.")
        if position in verified:
            return CoverageDecision(True, [], [])
        entry = ruleset.manifest.coverage_for(position)
        missing = entry.missing_mechanics() if entry is not None else list(MECHANIC_FIELDS)
        return CoverageDecision(
            False,
            [
                f"{position.value} does not have fully verified builder coverage, "
                "so it cannot be recommended."
            ],
            missing,
        )

    if verified:
        return CoverageDecision(True, [], [])

    notes = list(ruleset.manifest.notes) or [
        "No verified NBA 2K27 rules are loaded. Public build recommendations are disabled."
    ]
    return CoverageDecision(False, notes, list(MECHANIC_FIELDS))


def unsupported_optimize(
    ruleset: ActiveRuleset,
    decision: CoverageDecision,
    request_id: str,
    elapsed_ms: int,
) -> UnsupportedOptimizeResponse:
    warnings = [
        "Search was not run because verified coverage is missing.",
        *decision.notes,
    ]
    return UnsupportedOptimizeResponse(
        request_id=request_id,
        ruleset_id=ruleset.manifest.ruleset_id,
        scoring_version=SCORING_VERSION,
        optimizer_version=OPTIMIZER_VERSION,
        elapsed_ms=elapsed_ms,
        coverage=decision.as_report(),
        warnings=warnings,
        cache=CacheInfo(hit=False),
        recommendations=RecommendationSet(),
        status="unsupported",
        optimality_proven=False,
    )


def validation_result(
    ruleset: ActiveRuleset,
    decision: CoverageDecision,
    request_id: str,
) -> ValidateResponse:
    issues: list[FieldIssue] = []
    if not decision.supported:
        issues.append(
            FieldIssue(
                field="coverage",
                code="coverage_unsupported",
                message=(
                    "Verified rules do not cover this request, so in-game legality was not judged."
                ),
            )
        )
    return ValidateResponse(
        request_id=request_id,
        ruleset_id=ruleset.manifest.ruleset_id,
        supported=decision.supported,
        issues=issues,
        warnings=list(decision.notes),
    )
