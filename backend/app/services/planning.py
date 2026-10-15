import time
from dataclasses import dataclass

from app.domain import MECHANIC_FIELDS, OPTIMIZER_VERSION, SCORING_VERSION
from app.optimizer.solve import SolveBudget, response_from_outcome, solve_locked_body
from app.rules.engine import RuleFinding, audit_request
from app.rules.loader import ActiveRuleset
from app.schemas.optimize import (
    CacheInfo,
    CoverageReport,
    FieldIssue,
    OptimizeRequest,
    OptimizeResponse,
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


@dataclass(frozen=True)
class RequestAssessment:
    decision: CoverageDecision
    rejections: list[RuleFinding]


def assess_request(ruleset: ActiveRuleset, request: OptimizeRequest) -> RequestAssessment:
    """Combine coverage with explicit rule findings.

    An unlocked body is a preference, so it is not a rejection when verified
    profiles exist. Missing mechanics stay unsupported.
    """

    decision = assess_coverage(ruleset, request)
    rejections = [
        finding for finding in audit_request(ruleset.bundle, request) if finding.blocks_request()
    ]
    notes = list(decision.notes)
    missing = list(decision.missing_mechanics)
    for finding in rejections:
        if finding.message not in notes:
            notes.append(finding.message)
        if finding.mechanic not in missing:
            missing.append(finding.mechanic)
    supported = decision.supported and not rejections
    if ruleset.synthetic:
        supported = False
        message = "Synthetic rules are for tests only and cannot recommend builds."
        if message not in notes:
            notes.append(message)
        rejections = [
            RuleFinding(
                field="ruleset",
                mechanic="ruleset",
                status="unsupported",
                code="synthetic_ruleset",
                message=message,
            ),
            *rejections,
        ]
    return RequestAssessment(CoverageDecision(supported, notes, missing), rejections)


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
    request: OptimizeRequest,
    request_id: str,
) -> ValidateResponse:
    coverage = assess_coverage(ruleset, request)
    assessment = assess_request(ruleset, request)
    issues: list[FieldIssue] = []
    if not coverage.supported:
        issues.append(
            FieldIssue(
                field="coverage",
                code="coverage_unsupported",
                message=(
                    "Verified rules do not cover this request, so in-game legality was not judged."
                ),
            )
        )
    issues.extend(
        FieldIssue(field=finding.field, code=finding.code, message=finding.message)
        for finding in assessment.rejections
    )
    return ValidateResponse(
        request_id=request_id,
        ruleset_id=ruleset.manifest.ruleset_id,
        supported=assessment.decision.supported,
        issues=issues,
        warnings=list(assessment.decision.notes),
    )


def plan_optimize(
    ruleset: ActiveRuleset,
    request: OptimizeRequest,
    request_id: str,
    budget: SolveBudget,
) -> OptimizeResponse:
    """Return unsupported when coverage is missing, otherwise solve one body."""

    started = time.perf_counter()
    assessment = assess_request(ruleset, request)
    if not assessment.decision.supported:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return unsupported_optimize(ruleset, assessment.decision, request_id, elapsed_ms)
    outcome = solve_locked_body(ruleset.bundle, request, budget)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return response_from_outcome(outcome, ruleset, request_id, elapsed_ms)
