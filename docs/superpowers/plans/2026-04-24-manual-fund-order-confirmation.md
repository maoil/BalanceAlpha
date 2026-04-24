# Manual Fund Order Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pending confirmation flow for manual off-exchange fund buys, plus manual confirm and price-refresh auto-confirm.

**Architecture:** Keep `Trade` and `Position` as confirmed facts only. Add a dedicated `ManualFundOrder` model and `ManualFundOrderService` so manual fund buys create pending orders first, then confirm into a formal trade through one shared confirmation path used by both the manual confirm API and the refresh-prices fallback.

**Tech Stack:** Flask, SQLAlchemy, pytest

---

## File Structure

- Create: `app/models/manual_fund_order.py`
- Create: `app/services/manual_fund_order_service.py`
- Create: `app/api/manual_fund_orders.py`
- Modify: `app/models/__init__.py`
- Modify: `app/api/__init__.py`
- Modify: `app/api/trades.py`
- Modify: `app/schemas/serializers.py`
- Modify: `app/schemas/__init__.py`
- Modify: `app/services/trade_service.py`
- Modify: `app/services/fund_data_fetcher.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_api_endpoints.py`

### Task 1: Add the pending order model and serialization

**Files:**
- Create: `app/models/manual_fund_order.py`
- Modify: `app/models/__init__.py`
- Modify: `app/schemas/serializers.py`
- Modify: `app/schemas/__init__.py`
- Modify: `tests/conftest.py`

- [ ] Step 1: Write failing model/serializer tests for the new pending order shape.
- [ ] Step 2: Run targeted pytest to verify the new tests fail.
- [ ] Step 3: Add the `ManualFundOrder` SQLAlchemy model and export it.
- [ ] Step 4: Add serializer support for manual fund orders.
- [ ] Step 5: Run the targeted pytest again and make it pass.

### Task 2: Route manual fund buys into pending orders

**Files:**
- Create: `app/services/manual_fund_order_service.py`
- Modify: `app/services/trade_service.py`
- Modify: `app/api/trades.py`
- Modify: `tests/test_api_endpoints.py`

- [ ] Step 1: Write failing API tests showing off-exchange fund buys create `pending` orders while ETF buys still create `trade`.
- [ ] Step 2: Run targeted pytest to verify the tests fail for the expected reason.
- [ ] Step 3: Implement `ManualFundOrderService.create_pending_order()` and the `TradeService` branching logic.
- [ ] Step 4: Update the trades API response so manual fund buy creation returns the pending order payload.
- [ ] Step 5: Run the targeted pytest again and make it pass.

### Task 3: Add manual confirmation API

**Files:**
- Create: `app/api/manual_fund_orders.py`
- Modify: `app/api/__init__.py`
- Modify: `app/services/manual_fund_order_service.py`
- Modify: `tests/test_api_endpoints.py`

- [ ] Step 1: Write failing API tests for confirming a pending order, including the “not ready yet” path.
- [ ] Step 2: Run targeted pytest to verify failure.
- [ ] Step 3: Implement `confirm_order()` with shared validation, NAV checks, trade creation, and position update in one transaction.
- [ ] Step 4: Add the new API route and wire it into the blueprint registration.
- [ ] Step 5: Run the targeted pytest again and make it pass.

### Task 4: Add refresh-price auto-confirm fallback

**Files:**
- Modify: `app/services/manual_fund_order_service.py`
- Modify: `app/services/fund_data_fetcher.py`
- Modify: `tests/test_api_endpoints.py`

- [ ] Step 1: Write failing tests showing refresh-price processing auto-confirms ready pending orders.
- [ ] Step 2: Run targeted pytest to verify failure.
- [ ] Step 3: Implement `confirm_due_orders()` and call it from the existing refresh-prices flow.
- [ ] Step 4: Run the targeted pytest again and make it pass.

### Task 5: Run focused and broader verification

**Files:**
- Modify: `tests/test_api_endpoints.py`

- [ ] Step 1: Run the new focused API tests in `balance` environment.
- [ ] Step 2: Run the broader relevant suite in `balance` environment: `tests/test_api_endpoints.py` and `tests/test_dca_services.py`.
- [ ] Step 3: Inspect failures, fix only feature-related regressions, and rerun until clean.
