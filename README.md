# Unofficial NBA 2K27 Build Optimizer

Planning tool for NBA 2K27 MyPLAYER builds. This repository is at milestone M4: the builder and results pages on top of the guarded search. The shipped ruleset is still `nba2k27-unverified`, with an empty attribute catalog and no legal body ranges.

No NBA 2K27 attribute costs, body limits, badge rules, animations, Takeovers, or archetype names are included. Optimize and validate accept a well-formed request and return `unsupported`, naming each missing mechanic. They do not invent a build. Build type is `male` or `female`, and neither has a verified height, weight, or wingspan range.

When a request is fully covered by verified rules, the solver searches that one locked body and checks the recipe again with the rules engine. Today that coverage is empty, so the public search does not run. Toy numbers live in tests only.

See `docs/RULES_PROVENANCE.md` and `docs/VERIFICATION_PROTOCOL.md`.

This is not an official 2K or NBA product.

## Run it locally

The database password below is for local development only.

1. Start Postgres. The container is published on host port 5434, because this Mac already runs Postgres 16 on 5432 and Postgres 17 on 5433.

```bash
docker compose -f infra/docker-compose.yml up db -d
```

2. Start the API from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

3. Start the web app from `frontend/`:

```bash
npm install
npm run dev
```

Open http://localhost:5173. The home page calls `GET /api/v1/metadata` and shows loading, the unverified-rules result, or a connection error. Vite proxies `/api` and `/health` to http://localhost:8000.

The web app expects Node.js 24. If `node --version` is older, run `nvm use` in the repository root.

API docs are at http://localhost:8000/docs.

To run the API in Docker as well:

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Tests

```bash
cd backend && .venv/bin/pytest
cd frontend && npm test && npm run typecheck
```

Regenerate the TypeScript API types after a contract change:

```bash
cd backend && .venv/bin/python scripts/export_openapi.py ../frontend/openapi.json
cd frontend && npm run generate:api
```

## What this version does not do

- It does not recommend builds from the shipped ruleset. A locked body, a target rating, or a badge tier is not treated as legal just because the JSON shape is valid.
- It does not store shared builds or issue reports. Those routes return `501`, and the results page says sharing is off.
- The builder, results, compare, and refine views run in the browser. Refreshing the page clears the latest search. Attribute, badge, animation, and Takeover choices come from `GET /api/v1/metadata`, which is empty until rules are verified.
- Numeric limits on the request (for example a rating of 150 or a weight of 1000) are API transport limits, not in-game ranges.
- Synthetic fixtures under `backend/tests/fixtures/synthetic/` are toy data. The active loader rejects them. A passing solver test on that fixture is not an NBA 2K27 result.

The next milestone is sharing, issue reports, and the persistent search cache. Game values get added only after they are observed in the builder and checked in together.

To record search latency on the toy fixture:

```bash
cd backend && .venv/bin/python scripts/benchmark_search.py
```
