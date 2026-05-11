# Backtesting.py Native Backtest Redesign

## Context

BalanceAlpha currently has a custom backtest service that simulates account-level portfolio behavior from account, instrument, and strategy-template assignments. The target design replaces that model with a `backtesting.py` native single-instrument workflow.

The source implementation to vendor is located at:

`C:\Users\guangxin.yang\BalanceAlpha\backtesting.py-master\backtesting.py-master\backtesting`

The script `your_script.py` is the reference for the desired execution model:

1. Fetch daily OHLCV from a remote provider.
2. Build derived indicators on a warmup data window.
3. Slice the prepared data to the formal backtest start date.
4. Run `Backtest(data, StrategyClass, ...)`.
5. Persist printed statistics, equity curve, trades, and optionally an HTML chart.

## Goals

- Remove the old account-combination backtest semantics.
- Vendor the `backtesting.py` engine into BalanceAlpha so it can be adapted locally.
- Run backtests as single-instrument OHLCV simulations using `Backtest` and `Strategy`.
- Let each product configure one default backtest strategy.
- Prefer a configurable strategy DSL for common strategies.
- Keep file-based Python `Strategy` classes as an advanced fallback.
- Fetch remote OHLCV data through configurable provider URLs with priority-based fallback.
- Keep historical `BacktestRun` records and expose list, create, and detail APIs.
- Preserve a design path for future portfolio or combination strategies without reintroducing the old account-template model.

## Non-Goals

- Do not preserve the old account, template, and assignment based backtest behavior.
- Do not execute arbitrary Python code from untrusted users.
- Do not build a full online Python IDE for strategy code in the first version.
- Do not require local `MarketData` rows for every backtest. Remote provider fetch is the primary source.

## Architecture

The new backtest layer has five boundaries:

1. `app/vendor/backtesting`: vendored `backtesting.py` package.
2. Data providers: fetch and normalize remote OHLCV.
3. Strategy registry: resolve a product's configured strategy.
4. Strategy compiler: convert DSL strategy specs into a `Strategy` subclass.
5. Backtest runner: execute `Backtest`, serialize results, and persist a `BacktestRun`.

Business code should call only the BalanceAlpha wrapper services. API handlers and frontend code should not import vendored engine internals directly.

## Data Providers

Products can have one or more backtest data sources. The first version should support priority fallback:

- Try enabled sources by ascending priority.
- Apply provider-specific URL templates and parser adapters.
- Retry transient failures according to source config.
- Stop at the first provider that returns non-empty normalized OHLCV data.
- Raise a validation error if every source fails.

Suggested `BacktestDataSource` fields:

- `id`
- `instrument_id`
- `provider_type`
- `url_template`
- `priority`
- `enabled`
- `timeout_seconds`
- `retry_count`
- `adjustment`
- `notes`
- `created_at`
- `updated_at`

`url_template` may contain placeholders such as `{symbol}`, `{start}`, `{end}`, `{market}`, and `{adjustment}`. Provider adapters own the final request format and response parsing.

Provider adapters are implemented in code, not stored as arbitrary database code. Initial provider types:

- `tencent_daily_ohlcv`: stock or ETF daily K-line data similar to `fetch_daily_ohlcv()` in `your_script.py`.
- `eastmoney_fund_nav`: fund NAV data converted to OHLCV by setting `Open`, `High`, `Low`, and `Close` to NAV.

The normalized DataFrame must have:

- A sorted ascending `DatetimeIndex`.
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`

Additional columns are allowed and may be consumed by strategies.

Remote data may later be cached into `MarketData`, but the first design treats remote providers as the source of truth for backtesting.

## Strategy Model

Each product points to one default strategy. Strategy configuration uses two modes.

### Config Strategy

The default mode is a JSON strategy spec stored in the database. It describes indicators, entry rules, exit rules, position sizing, and backtest execution flags.

Suggested `BacktestStrategy` fields:

- `id`
- `strategy_key`
- `strategy_name`
- `mode`
- `spec_json`
- `default_params_json`
- `default_backtest_config_json`
- `description`
- `status`
- `created_at`
- `updated_at`

`mode = "config"` means `spec_json` is compiled into a generated `Strategy` subclass.

Example spec for the Donchian momentum strategy:

```json
{
  "name": "Donchian Momentum",
  "indicators": [
    { "name": "SMA20", "type": "sma", "source": "Close", "period": 20 },
    { "name": "HH10", "type": "rolling_max", "source": "Close", "period": 10 },
    { "name": "LL10", "type": "rolling_min", "source": "Close", "period": 10 },
    { "name": "ROC10", "type": "pct_change", "source": "Close", "period": 10 }
  ],
  "entry": {
    "all": [
      { "left": "Close", "op": ">=", "right": "HH10[-2]" },
      { "left": "ROC10", "op": ">=", "right": 0.06 },
      { "left": "Close", "op": ">", "right": "SMA20" }
    ]
  },
  "exit": {
    "any": [
      { "left": "Close", "op": "<=", "right": "LL10[-2]" },
      { "left": "Close", "op": "<", "right": "SMA20" }
    ]
  },
  "position": {
    "direction": "long_only",
    "size": "all_available"
  }
}
```

The compiler prepares indicators before formal slicing, then creates a `Strategy` class whose `init()` registers indicators with `self.I(...)` and whose `next()` applies the entry and exit rule trees.

Initial DSL support:

- Indicators: `sma`, `ema`, `rolling_max`, `rolling_min`, `pct_change`, `rsi`.
- Operators: `>`, `>=`, `<`, `<=`, `==`, `cross_above`, `cross_below`.
- Logic: `all`, `any`, nested groups.
- References: current column or indicator values, plus lag syntax such as `HH10[-2]`.
- Direction: `long_only`.
- Position size: `all_available`, fixed cash amount, or equity percentage.
- Backtest flags: `exclusive_orders`, `finalize_trades`, `trade_on_close`, `commission`, and `cash`.

### Python Module Strategy

Advanced strategies can be implemented as committed Python files. The database stores only references and params.

`mode = "python_module"` fields in `spec_json`:

```json
{
  "module_path": "app.backtest_strategies.donchian_custom",
  "class_name": "DonchianMomentumChaser",
  "prepare_func_name": "prepare_data"
}
```

The referenced class must inherit the vendored `Strategy`. If `prepare_func_name` exists, the runner calls it before formal date slicing.

This mode is the fallback when a strategy cannot be expressed cleanly in the JSON DSL. It keeps complex code in git, supports normal IDE workflows, and avoids storing large Python modules in the database.

## Configuration Surface

The first implementation should include minimal CRUD support for strategy and data-source configuration so strategies are not hard-coded into migrations:

- List, create, update, and deactivate `BacktestStrategy` rows.
- List, create, update, and deactivate `BacktestDataSource` rows for a product.
- Assign a default strategy to a product.
- Edit product-level strategy parameter overrides.

The frontend can start with JSON text areas for `spec_json`, `default_params_json`, `default_backtest_config_json`, and `backtest_params_json`. A structured rule-builder UI can be added later after the DSL shape stabilizes.

## Product Binding

Add strategy binding fields to `Instrument`:

- `backtest_strategy_id`
- `backtest_params_json`

`backtest_params_json` overrides strategy defaults for that product. Product-level parameters are merged after `BacktestStrategy.default_params_json`.

Each product should also have one or more `BacktestDataSource` rows.

## BacktestRun Model

Keep a historical run table but change its semantics from account-combination runs to single-product strategy runs.

Suggested fields:

- `id`
- `run_name`
- `instrument_id`
- `strategy_id`
- `start_date`
- `end_date`
- `warmup_start_date`
- `params_json`
- `result_json`
- `status`
- `created_at`

`template_id` is no longer part of the backtest model.

## Execution Flow

`BacktestService.run_backtest()` should:

1. Validate `instrument_id`, `start_date`, `end_date`, and `initial_capital`.
2. Resolve the product's active `BacktestStrategy`.
3. Resolve enabled `BacktestDataSource` rows by priority.
4. Compute `warmup_start_date`. If explicitly supplied, use it. Otherwise derive it from strategy warmup needs or a conservative default such as 250 trading days.
5. Fetch raw OHLCV from the first successful provider for `warmup_start_date` through `end_date`.
6. Normalize and validate the DataFrame.
7. Resolve or compile the strategy:
   - Config mode: compile `spec_json` into a generated `Strategy` subclass and prepare indicator columns.
   - Python module mode: import the module, call optional `prepare_data`, and load `class_name`.
8. Slice prepared data to `start_date:end_date`.
9. Run:

```python
bt = Backtest(
    data,
    StrategyClass,
    cash=initial_capital,
    commission=commission,
    exclusive_orders=True,
    finalize_trades=True,
)
stats = bt.run(**strategy_params)
```

10. Serialize:
    - Scalar stats.
    - `_equity_curve`.
    - `_trades`.
    - Data source metadata.
    - Strategy metadata and params.
    - Optional chart HTML path if generated.
11. Mark run as completed or failed and persist the result JSON.

## Result JSON Shape

The stored result should be stable for frontend display:

```json
{
  "scope": {
    "instrument_id": 1,
    "symbol": "159819.SZ",
    "name": "AI ETF",
    "strategy_id": 1,
    "strategy_name": "Donchian Momentum",
    "provider_type": "tencent_daily_ohlcv"
  },
  "summary": {
    "start": "2026-02-24",
    "end": "2026-05-11",
    "equity_final": 103000.0,
    "return_pct": 3.0,
    "buy_hold_return_pct": 2.1,
    "max_drawdown_pct": -4.2,
    "sharpe_ratio": 0.8,
    "trade_count": 3,
    "win_rate_pct": 66.7
  },
  "equity_curve": [],
  "trades": [],
  "stats": {},
  "chart": {
    "html_path": null
  }
}
```

The exact stats keys can mirror `backtesting.py`, but the `summary` object should use BalanceAlpha-friendly snake_case keys.

## API Changes

Keep existing endpoints:

- `GET /api/v1/backtests`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/<id>`

Change create payload to:

```json
{
  "run_name": "AI ETF Donchian",
  "instrument_id": 1,
  "start_date": "2026-02-24",
  "end_date": "2026-05-11",
  "warmup_start_date": "2025-09-01",
  "initial_capital": 100000,
  "commission": 0.0003,
  "strategy_params": {}
}
```

Remove `account_id` and `template_id` from the backtest create contract.

Add or extend product configuration APIs in this redesign so the frontend can manage:

- Product default backtest strategy.
- Product data sources.
- Product strategy parameter overrides.

## Frontend Changes

The backtest page should:

- Remove account and strategy-template selectors.
- Select one product.
- Display the product's configured strategy name.
- Accept date range, optional warmup start date, initial capital, and commission.
- Run the backtest.
- Show summary stats, trades, equity curve, provider used, and error state.
- Keep historical run list and detail selection.

The first implementation can show result JSON or summary tables. Rich charts can follow after the backend result shape is stable.

## Deletion and Migration

Delete or replace:

- The custom account portfolio simulation in `app/services/backtest_service.py`.
- Backtest API parsing of `account_id` and `template_id`.
- Frontend account/template fields on `BacktestsPage`.
- Tests that assert account-combination behavior.

Keep and migrate:

- `BacktestRun` as historical record storage.
- Backtest list/detail/create API route names.
- Basic frontend history/detail structure.

Old `backtest_runs` rows may become incompatible because their `params_json` and `result_json` were produced by the old model. The first migration can keep them in the table but the UI should tolerate old rows missing the new `scope.strategy_id` and `scope.instrument_id` fields.

## Safety

The first version assumes a trusted local single-user environment.

Config-mode strategies do not execute user Python and should be preferred for normal online configuration.

Python-module strategies execute committed local code only. Do not support arbitrary Python code stored in the database in the first version.

If BalanceAlpha later supports untrusted users, strategy execution must move into an isolated process or container with resource limits and a restricted filesystem/network policy.

## Testing Plan

Backend tests:

- Provider fallback uses the next enabled source after a failure.
- Tencent-style OHLCV payload normalizes to the required DataFrame columns.
- Eastmoney NAV payload normalizes fund NAV to OHLCV.
- Product without a strategy returns a validation error.
- Config-mode Donchian strategy compiles and runs.
- Python-module strategy loads only a valid `Strategy` subclass.
- Warmup data is used for indicators before slicing the formal range.
- Run result stores serializable summary, equity curve, and trades.
- API create no longer requires `account_id` or `template_id`.

Frontend tests:

- Backtest form contains product, dates, warmup date, initial capital, and commission.
- Account and template selectors are removed.
- Successful create refreshes historical runs and selects the created run.
- Summary display tolerates failed runs and old legacy run JSON.

## Future Portfolio Strategy Path

Future combination strategies should not revive the old account-template simulator. Instead, add a separate portfolio strategy layer that composes:

- Multiple product data sources.
- Multiple product strategy specs or signals.
- Portfolio-level allocation and rebalance rules.

That layer can still use the same provider registry, strategy DSL, result serialization, and run-history model, but it should be represented as a new strategy mode or portfolio-run type with explicit interfaces.
