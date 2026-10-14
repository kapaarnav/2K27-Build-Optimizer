# Unofficial NBA 2K27 Build Optimizer

Planning tool for NBA 2K27 MyPLAYER builds. This repository is at milestone M0: the API contract, an empty verified-rules manifest, and a web page that shows whether recommendations are available.

No NBA 2K27 attribute costs, body limits, badge rules, animations, Takeovers, or archetype names are included. The shipped ruleset is `nba2k27-unverified`. Optimize and validate accept a well-formed request and return `unsupported`. They do not invent a build.

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

- It does not recommend builds, allocate Cap Breakers, or name archetypes.
- It does not store shared builds or issue reports. Those routes return `501`.
- It does not treat a locked body, a target rating, or a badge tier as legal just because the JSON shape is valid. Game legality waits for verified rules.
- Numeric limits on the request (for example a rating of 150 or a weight of 1000) are API transport limits, not in-game ranges.

The next milestone is a rules loader and verification harness. Game values get added only after they are observed in the builder and checked in together.
