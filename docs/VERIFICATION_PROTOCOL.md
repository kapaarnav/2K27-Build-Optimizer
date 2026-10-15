# Verification protocol

A mechanic is usable for a public recommendation only after a sourced observation is checked in as `verified`. Until then the rules engine returns `unsupported` and does not guess a number, a name, or a legal range.

## Statuses

- `verified`: eligible to be used, and only for the recorded case.
- `needs_verification`: previously checked, and a later patch may affect it.
- `unsupported`: the mechanic or case is missing. This is not the same as illegal or ineligible.
- `contradictory`: sources disagree, or a verified link closure forces a rating above a required exact target.
- `retired`: no longer used.

## What the engine will not infer

- An empty catalog does not mean every attribute id is illegal. It means attributes cannot be matched yet.
- An empty body list does not make a locked body illegal.
- A complete body list can mark a missing tuple as outside that list. A partial list cannot.
- Linked attributes are applied only from a closure marked complete. A single known link is not treated as the full set.
- Overall and archetype names come from exact observed vectors. Nearby vectors are unsupported, not estimated.
- A Cap Breaker gain is an observed step. One application that grants +2 does not imply the next application.
- A badge, animation, or Takeover with no predicate is unsupported. Ineligible is used only when a verified predicate fails.
- The per-attribute Cap Breaker limit stays unset until a verified record exists.

## Single-body solver

The solver searches one fully locked body. A base vector is eligible only when the rules engine returns a verified overall and a verified archetype name for that exact vector, the vector is inside the body bounds, and it is a fixed point of the verified link closure.

Cap Breaker results come from verified gain steps. A step that grants +2 does not authorize a different application count, and it is not treated as +1.

`infeasible_proven` is used only when the request contradicts verified bounds, the link closure, a required unlock predicate, or a non-negative Cap Breaker gain. The loader accepts only non-negative gains, and proofs use that limit. A miss that those rules still allow is `unsupported`: the verified tables do not contain a recipe, which is different from the game forbidding the request.

`no_feasible_found_in_budget` means the budget ended without a recipe and without that proof.

Public recommendations stay off while the active ruleset is synthetic or unverified.

## Adding a verified rule

1. Record the observation date, app or tuning version, position, build type, exact measurements, and the values shown in the builder.
2. Add the record to the matching file under `backend/app/data/active/` with provenance. Keep evidence pointers, not account screenshots.
3. Update `manifest.yaml` coverage only for mechanics that now have backing records.
4. Add a regression case. Synthetic cases stay in `backend/tests/fixtures/synthetic/` and keep `synthetic: true`.
5. Run the backend tests. The active loader fails if coverage claims a mechanic the files do not back.

```bash
cd backend && .venv/bin/pytest
```

Toy fixtures may exercise the loader and engine. They must not be loaded as the active ruleset, and `recommendations_enabled` stays false while any record is synthetic.
