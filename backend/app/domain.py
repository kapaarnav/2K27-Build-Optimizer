from enum import StrEnum


class Position(StrEnum):
    pg = "PG"
    sg = "SG"
    sf = "SF"
    pf = "PF"
    center = "C"


class Importance(StrEnum):
    required = "required"
    prioritized = "prioritized"
    normal = "normal"


class SearchMode(StrEnum):
    generate = "generate"
    refine = "refine"


class BadgeTier(StrEnum):
    """Request vocabulary from the product contract, not a verified eligibility table."""

    bronze = "bronze"
    silver = "silver"
    gold = "gold"
    hall_of_fame = "hall_of_fame"


class PoolKind(StrEnum):
    unrestricted = "unrestricted"
    specialization = "specialization"


class VerificationStatus(StrEnum):
    verified = "verified"
    needs_verification = "needs_verification"
    unsupported = "unsupported"
    contradictory = "contradictory"
    retired = "retired"


class IssueCategory(StrEnum):
    incorrect_build = "incorrect_build"
    missed_requirement = "missed_requirement"
    display_problem = "display_problem"
    other = "other"


MECHANIC_FIELDS: tuple[str, ...] = (
    "body_profiles",
    "attribute_costs",
    "cap_breakers",
    "badge_eligibility",
    "animations",
    "takeovers",
    "archetype_names",
)

# Scoring presets for the optimizer. These are product inputs, not game rules.
PLAYSTYLES: tuple[tuple[str, str], ...] = (
    ("automatic", "Automatic"),
    ("balanced", "Balanced"),
    ("shooting", "Shooting"),
    ("slashing", "Slashing"),
    ("playmaking", "Playmaking"),
    ("defense", "Defense"),
    ("inside_rebounding", "Inside / rebounding"),
)

PLAYSTYLE_IDS: frozenset[str] = frozenset(playstyle_id for playstyle_id, _label in PLAYSTYLES)

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

SCORING_VERSION = "score-unconfigured"
OPTIMIZER_VERSION = "optimizer-none"

DISCLAIMER = (
    "Unofficial NBA 2K27 build planning tool. "
    "Not affiliated with or endorsed by 2K or the NBA. "
    "A build is recommended only when every mechanic it depends on is verified."
)
