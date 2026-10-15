# Rules provenance

The shipped ruleset is `nba2k27-unverified`. It contains an empty attribute catalog, no body profiles, and no cost, name, link, badge, animation, Takeover, or Cap Breaker observations. Public recommendations stay off.

Build type is part of the body model (`male` or `female`). No height, weight, or wingspan range is verified for either.

The attribute file can hold `id`, `label`, `category`, and provenance. The product spec calls for 21 sourced attribute ids. None are invented here, so the catalog is empty and `catalog_complete` is false.

## Active files

| File | What it holds when verified |
| --- | --- |
| `manifest.yaml` | Ruleset id, coverage by position and mechanic, synthetic flag |
| `attributes.yaml` | Canonical attribute dictionary |
| `bodies.yaml` | Exact bodies and whether each build type and position list is complete or partial |
| `links.yaml` | Link closure. It is applied only when `complete` and `verified` |
| `costs.yaml` | Exact body-plus-attribute-vector overall observations |
| `names.yaml` | Exact archetype names for those same vectors |
| `eligibility.yaml` | Badge, animation, and Takeover predicates |
| `cap_breakers.yaml` | Exact gain steps, specialization permissions, and an application limit only if one was verified |

A verified record needs `source`, `observed_at`, and `evidence_ref`. Evidence is a pointer such as a note id. Screenshots and account data stay out of git.

`synthetic: true` is rejected by the active loader. Toy numbers live under `backend/tests/fixtures/synthetic/` and cannot enable recommendations. The single-body solver reads only rows the rules engine accepts. It does not fill a missing cost, name, or Cap Breaker step with a formula.

No third-party builder tables were copied into this ruleset. That dataset was not audited or imported in this milestone.

## Coverage

A position can be recommended only when every mechanic in its coverage entry is `verified` and the files contain verified records for those mechanics. Marking a mechanic verified without those records fails the loader. A partial body list does not make an unseen body illegal. A missing predicate is unsupported, which is different from ineligible.
