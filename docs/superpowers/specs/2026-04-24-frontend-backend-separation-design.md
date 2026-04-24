# Frontend Backend Separation Design

- Date: 2026-04-24
- Scope: Convert BalanceAlpha from a Flask-rendered app into a backend API plus an independent Vue SPA.
- Status: Approved by user for autonomous execution.

## Goals

- Keep the existing Flask, SQLAlchemy, SQLite, model, and service layers.
- Add a JSON API under `/api/v1`.
- Exempt API routes from template-oriented CSRF handling so an independent SPA can call them.
- Keep legacy Jinja routes during migration.
- Scaffold a separate Vue 3 + Vite + TypeScript frontend project.
- Build the first phase as a stable API and frontend shell, not a full page-by-page rewrite.

## Non-Goals

- Do not replace Flask with FastAPI or another backend framework in this phase.
- Do not change the database engine.
- Do not introduce multi-user auth or permission design in this phase.
- Do not delete existing Jinja templates until SPA parity exists.
- Do not rewrite business services while exposing APIs.

## Architecture

The backend remains the source of truth for data and business rules. Existing `app/services/*` methods continue to handle calculations, signal generation, trade creation, and position refresh.

The new API layer has three responsibilities:

- Parse request parameters and JSON bodies.
- Call services and models.
- Serialize responses into stable JSON shapes.

The frontend is a separate Vite project. It owns routing, layout, state, and all user interaction. It calls only `/api/v1/*` endpoints and does not depend on Jinja-rendered HTML.

## Backend Structure

```text
app/
  api/
    __init__.py
    accounts.py
    dashboard.py
    instruments.py
    positions.py
    signals.py
    trades.py
    settings.py
  schemas/
    __init__.py
    serializers.py
  services/
  models/
  views/
```

## API Conventions

- Success responses use `{ "data": ... }`.
- List responses may include `{ "meta": ... }` when useful.
- Errors use `{ "error": { "code": "...", "message": "..." } }`.
- Dates are ISO strings.
- Numeric fields are returned as numbers, with `null` preserved when the model field is unset.
- API routes are versioned under `/api/v1`.

## First API Surface

- `GET /api/v1/health`
- `GET /api/v1/accounts`
- `GET /api/v1/dashboard`
- `GET /api/v1/positions`
- `GET /api/v1/positions/<id>`
- `PATCH /api/v1/positions/<id>`
- `POST /api/v1/positions/refresh`
- `GET /api/v1/instruments`
- `POST /api/v1/instruments`
- `GET /api/v1/instruments/<id>`
- `PATCH /api/v1/instruments/<id>`
- `GET /api/v1/trades`
- `POST /api/v1/trades`
- `GET /api/v1/signals`
- `POST /api/v1/signals/generate`
- `GET /api/v1/signals/<id>`
- `GET /api/v1/settings/strategy-templates`

## Frontend Structure

The independent frontend project is created as a sibling directory:

```text
BalanceAlpha-Web/
  src/
    api/
    router/
    stores/
    layouts/
    views/
    components/
    types/
```

The frontend uses Vue 3, Vite, TypeScript, Vue Router, Pinia, Axios, Element Plus, and ECharts.

## Local Development

- Flask API: `http://localhost:5000`
- Vue SPA: `http://localhost:5173`
- Vite proxies `/api` to Flask.

The backend also allows CORS for `http://localhost:5173` by default so direct local API calls can work during development.

## Migration Order

1. Dashboard: establishes API and frontend layout.
2. Positions: validates list/detail/update/refresh interactions.
3. Signals: validates generation, list, detail, and action workflows.
4. Instruments: validates CRUD and DCA form data.
5. Trades: validates sensitive write flows.
6. Settings: validates strategy template editing after core workflows are stable.

## Testing

Backend tests cover API contracts with Flask test client:

- JSON response envelope.
- Dashboard aggregate payload.
- Position list/detail/update behavior.
- Instrument list/create/update behavior.
- Trade list/create behavior.
- CORS headers and API CSRF exemption.

Frontend verification covers:

- TypeScript build.
- Vite production build.
- API client base URL/proxy configuration.

