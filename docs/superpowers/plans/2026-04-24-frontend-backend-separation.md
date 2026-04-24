# Frontend Backend Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned Flask JSON API and scaffold an independent Vue SPA for BalanceAlpha.

**Architecture:** Keep the existing Flask service/model layers and add a thin API layer plus serializers. Create the Vue app as a separate sibling project that talks to `/api/v1` through a shared Axios client and Vite proxy.

**Tech Stack:** Flask, Flask-SQLAlchemy, pytest, Vue 3, Vite, TypeScript, Vue Router, Pinia, Axios, Element Plus, ECharts

---

### Task 1: Add Backend API Contract Tests

**Files:**
- Create: `tests/test_api_endpoints.py`

- [ ] Write tests for `GET /api/v1/health`, `GET /api/v1/dashboard`, `GET /api/v1/positions`, `PATCH /api/v1/positions/<id>`, and API CORS headers.
- [ ] Run `pytest tests/test_api_endpoints.py -v`.
- [ ] Confirm the tests fail because `/api/v1` routes do not exist.

### Task 2: Add API Blueprint And Serializers

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/responses.py`
- Create: `app/api/accounts.py`
- Create: `app/api/dashboard.py`
- Create: `app/api/positions.py`
- Create: `app/api/instruments.py`
- Create: `app/api/trades.py`
- Create: `app/api/signals.py`
- Create: `app/api/settings.py`
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/serializers.py`
- Modify: `app/__init__.py`
- Modify: `app/config.py`

- [ ] Register a `/api/v1` blueprint from `create_app`.
- [ ] Add lightweight CORS handling for configured API origins.
- [ ] Exempt only the API blueprint from CSRF.
- [ ] Add serializer functions for accounts, instruments, positions, trades, signals, and strategy templates.
- [ ] Implement the first API endpoints using existing services.
- [ ] Run `pytest tests/test_api_endpoints.py -v` and confirm pass.

### Task 3: Add Frontend Project Skeleton

**Files:**
- Create sibling project directory: `../BalanceAlpha-Web`
- Create: `../BalanceAlpha-Web/package.json`
- Create: `../BalanceAlpha-Web/vite.config.ts`
- Create: `../BalanceAlpha-Web/tsconfig.json`
- Create: `../BalanceAlpha-Web/index.html`
- Create: `../BalanceAlpha-Web/src/main.ts`
- Create: `../BalanceAlpha-Web/src/App.vue`
- Create: `../BalanceAlpha-Web/src/api/client.ts`
- Create: `../BalanceAlpha-Web/src/api/dashboard.ts`
- Create: `../BalanceAlpha-Web/src/api/positions.ts`
- Create: `../BalanceAlpha-Web/src/router/index.ts`
- Create: `../BalanceAlpha-Web/src/layouts/AppLayout.vue`
- Create: `../BalanceAlpha-Web/src/views/DashboardView.vue`
- Create: `../BalanceAlpha-Web/src/views/PositionsView.vue`
- Create: `../BalanceAlpha-Web/src/views/SignalsView.vue`
- Create: `../BalanceAlpha-Web/src/views/InstrumentsView.vue`
- Create: `../BalanceAlpha-Web/src/views/TradesView.vue`
- Create: `../BalanceAlpha-Web/src/views/SettingsView.vue`
- Create: `../BalanceAlpha-Web/src/styles/main.css`

- [ ] Build a functional operations-style shell with navigation and placeholder views.
- [ ] Add API client and typed dashboard/positions requests.
- [ ] Configure Vite proxy from `/api` to `http://localhost:5000`.
- [ ] Run `npm install` in `../BalanceAlpha-Web`.
- [ ] Run `npm run build` in `../BalanceAlpha-Web`.

### Task 4: Regression Verification

**Files:**
- Test: `tests/test_api_endpoints.py`
- Test: existing backend tests touched by app creation and services.

- [ ] Run `pytest tests/test_api_endpoints.py -v`.
- [ ] Run `python -m compileall app`.
- [ ] Run `npm run build` in `../BalanceAlpha-Web`.
- [ ] Review `git diff --stat` and confirm changes are scoped to API, docs, and frontend scaffold.

