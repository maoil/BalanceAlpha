# Backtesting.py 原生回测重构设计

## 背景

BalanceAlpha 现有回测服务是账户组合式模拟：按账户、产品、策略模板绑定关系生成组合级回测结果。新的目标是删除这套旧回测语义，改为 `backtesting.py` 原生的单产品 OHLCV 回测模型。

参考脚本：

`C:\Users\guangxin.yang\BalanceAlpha\backtesting.py-master\backtesting.py-master\your_script.py`

内置引擎来源：

`C:\Users\guangxin.yang\BalanceAlpha\backtesting.py-master\backtesting.py-master\backtesting`

参考脚本的核心执行方式是：

1. 从远程 URL 拉取日线 OHLCV。
2. 用预热区间数据计算指标。
3. 从正式开始日裁剪数据。
4. 执行 `Backtest(data, StrategyClass, ...)`。
5. 输出统计、权益曲线、交易记录和可选 HTML 图表。

## 第一阶段目标

- 删除 BalanceAlpha 原有账户组合式回测功能。
- 将 `backtesting.py` 源码复制进 BalanceAlpha，作为本地 vendor 引擎。
- 第一阶段只支持单产品回测，不做组合回测。
- 回测策略、数据源、产品绑定暂时全部由开发侧 Python 配置，不做线上 CRUD、不做数据库策略 DSL。
- 产品通过稳定配置键绑定到 Python 回测配置。
- 回测结果继续保存到 `BacktestRun`，保留历史列表、创建、详情 API。
- 为后续“持仓/观察池策略提醒”和“组合策略”保留接口边界。

## 第一阶段非目标

- 不保留旧的账户、策略模板、策略绑定组合回测语义。
- 不做在线 Python 策略编辑器。
- 不做策略 DSL 配置界面。
- 不做 `BacktestStrategy` / `BacktestDataSource` 数据库 CRUD。
- 不把 Strategy Python 代码或 Strategy JSON 存入数据库。
- 不要求回测必须读取本地 `MarketData`。远程行情源是第一阶段主路径。
- 不自动下单。所有回测和提醒只生成结果或建议。

## 架构

第一阶段回测层由四个边界组成：

1. `app/vendor/backtesting`：复制进项目的 `backtesting.py` 引擎。
2. 数据源适配器：用 Python 实现远程行情拉取和 OHLCV 标准化。
3. Python 回测配置注册表：绑定产品、数据源、策略类、预处理函数和默认参数。
4. 回测执行器：执行 `Backtest`，序列化结果，持久化 `BacktestRun`。

API 和前端只调用 BalanceAlpha 封装后的服务，不直接依赖 vendor 引擎内部模块。

## Python 配置注册表

第一阶段用 Python 文件集中配置回测，不依赖数据库配置。建议新增：

```text
app/backtesting/
  __init__.py
  registry.py
  providers.py
  result_serializer.py
  strategies/
    __init__.py
    donchian_momentum.py
    fund_momentum_breakout.py
```

示例注册表：

```python
from app.backtesting.providers import eastmoney_fund_nav, tencent_daily_ohlcv
from app.backtesting.strategies.donchian_momentum import (
    DonchianMomentumChaser,
    add_donchian_indicators,
)
from app.backtesting.strategies.fund_momentum_breakout import (
    FundMomentumBreakout,
    add_fund_indicators,
)

BACKTEST_CONFIGS = {
    "ai_etf_donchian": {
        "name": "人工智能 ETF - Donchian Momentum",
        "match": {"symbol": "159819", "market": "SZ"},
        "provider": tencent_daily_ohlcv,
        "provider_symbol": "159819.SZ",
        "strategy_class": DonchianMomentumChaser,
        "prepare_data": add_donchian_indicators,
        "default_params": {"min_momentum": 0.06},
        "warmup_days": 120,
        "backtest_config": {
            "commission": 0.0003,
            "exclusive_orders": True,
            "finalize_trades": True,
        },
    },
    "fund_020840_momentum": {
        "name": "基金 020840 - Momentum Breakout",
        "match": {"symbol": "020840"},
        "provider": eastmoney_fund_nav,
        "provider_symbol": "020840",
        "strategy_class": FundMomentumBreakout,
        "prepare_data": add_fund_indicators,
        "default_params": {},
        "warmup_days": 250,
        "backtest_config": {
            "commission": 0.0,
            "exclusive_orders": True,
            "finalize_trades": True,
        },
    },
}
```

每个配置项代表一个可运行回测方案：

- `name`：展示名称。
- `match`：无显式绑定键时，用产品代码/市场匹配。
- `provider`：远程数据源函数。
- `provider_symbol`：传给数据源的真实行情代码。
- `strategy_class`：继承 `backtesting.Strategy` 的类。
- `prepare_data`：可选数据预处理函数，用于计算 SMA、Donchian、ROC 等指标。
- `default_params`：传给 `bt.run(**params)` 的默认策略参数。
- `warmup_days`：未显式传 `warmup_start_date` 时的默认预热长度。
- `backtest_config`：传给 `Backtest(...)` 的默认配置。

## 产品绑定

推荐在 `Instrument` 增加一个轻量字段：

- `backtest_config_key`

该字段只保存 Python 注册表中的配置键，不保存策略代码或完整配置。

绑定优先级：

1. 如果 `instrument.backtest_config_key` 有值，则用它查找 `BACKTEST_CONFIGS`。
2. 如果没有配置键，则用 `Instrument.symbol` + `Instrument.market` 匹配注册表的 `match`。
3. 如果仍未匹配，返回“该产品未配置回测策略”的校验错误。

示例：

```text
Instrument.symbol = "159819"
Instrument.market = "SZ"
Instrument.backtest_config_key = "ai_etf_donchian"
```

这样可以避免直接依赖数据库自增 ID，也避免产品代码格式变化导致绑定失效。后续切换策略时，只需要改 `backtest_config_key`。

如果第一阶段不想改产品表，也可以先只用 `symbol/market` 自动匹配；但长期建议加入 `backtest_config_key`，边界更清楚。

## 数据源

第一阶段数据源由 Python 函数实现。函数职责是拉取远程数据，并返回标准 OHLCV DataFrame。

统一接口建议：

```python
def fetch_ohlcv(symbol: str, start: str, end: str) -> pd.DataFrame:
    ...
```

标准返回格式：

- 升序 `DatetimeIndex`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`

第一阶段内置数据源：

- `tencent_daily_ohlcv`：股票/ETF 日线 K 线，参考 `your_script.py` 的 `fetch_daily_ohlcv()`。
- `eastmoney_fund_nav`：基金净值，转换为 OHLCV，`Open/High/Low/Close` 都取净值。

数据源 URL 和重试逻辑先写在 Python provider 中。后续如果需要多 URL 轮询，可以在 provider 函数内部配置候选 URL 列表并按顺序 fallback。

## Strategy 文件约定

策略代码放在 `app/backtesting/strategies/` 下，每个文件可以包含：

```python
def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    # 计算指标列，如 SMA20、HH10、LL10、ROC10
    return df


class DonchianMomentumChaser(Strategy):
    min_momentum = 0.06

    def init(self):
        ...

    def next(self):
        ...
```

约束：

- `strategy_class` 必须继承 vendor 后的 `Strategy`。
- 指标计算优先放到 `prepare_data()`，保持 `Strategy` 类接近 `your_script.py` 的写法。
- 策略参数用类变量声明，运行时通过 `bt.run(**params)` 覆盖。
- 复杂策略直接写 Python，不在第一阶段设计 DSL。

## BacktestRun 模型

保留回测运行记录，但语义改为单产品策略运行。

建议字段：

- `id`
- `run_name`
- `instrument_id`
- `backtest_config_key`
- `start_date`
- `end_date`
- `warmup_start_date`
- `params_json`
- `result_json`
- `status`
- `created_at`

`template_id` 不再属于新回测模型。旧字段如果短期保留，应只用于兼容旧数据，不参与新逻辑。

`params_json` 保存本次运行快照：

- 产品信息。
- `backtest_config_key`。
- provider 名称和 provider symbol。
- strategy class 名称。
- 合并后的 strategy params。
- 合并后的 `Backtest(...)` 配置。
- warmup 起止日期。

## 执行流程

`BacktestService.run_backtest()` 新流程：

1. 校验 `instrument_id`、`start_date`、`end_date`、`initial_capital`。
2. 从产品解析 `backtest_config_key`，或用 `symbol/market` 自动匹配 Python 注册表。
3. 如果没有匹配配置，返回校验错误。
4. 计算 `warmup_start_date`。请求显式传入则使用请求值，否则根据配置中的 `warmup_days` 回推。
5. 调用配置中的 provider，获取 `warmup_start_date` 到 `end_date` 的原始 OHLCV。
6. 校验 DataFrame 列、日期排序、空值。
7. 调用配置中的 `prepare_data(raw_data)`，计算指标列。
8. 将准备好的数据裁剪到 `start_date:end_date`。
9. 合并运行参数：
   - 注册表 `default_params`
   - 请求中的 `strategy_params`
10. 合并 Backtest 参数：
    - 注册表 `backtest_config`
    - 请求中的 `commission`
    - 请求中的 `initial_capital` 映射为 `cash`
11. 执行：

```python
bt = Backtest(
    data,
    config["strategy_class"],
    cash=initial_capital,
    commission=commission,
    exclusive_orders=config["backtest_config"].get("exclusive_orders", True),
    finalize_trades=config["backtest_config"].get("finalize_trades", True),
)
stats = bt.run(**strategy_params)
```

12. 序列化 stats、`_equity_curve`、`_trades`、配置快照和错误信息。
13. 写入 `BacktestRun`，成功标记为 `completed`，失败标记为 `failed`。

## 结果 JSON 结构

新结果结构应稳定，便于前端展示：

```json
{
  "scope": {
    "instrument_id": 1,
    "symbol": "159819",
    "market": "SZ",
    "name": "人工智能 ETF",
    "backtest_config_key": "ai_etf_donchian",
    "config_name": "人工智能 ETF - Donchian Momentum",
    "provider": "tencent_daily_ohlcv",
    "provider_symbol": "159819.SZ",
    "strategy_class": "DonchianMomentumChaser"
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
  },
  "error": null
}
```

`stats` 可以保留 `backtesting.py` 原始统计键名；`summary` 用 BalanceAlpha 自己的 snake_case 键，避免前端直接依赖第三方库输出格式。

## API 变更

保留现有端点名称：

- `GET /api/v1/backtests`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/<id>`

创建请求 payload：

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

变更：

- 移除 `account_id`。
- 移除 `template_id`。
- 不暴露线上策略配置 API。
- 可在产品详情 API 中返回 `backtest_config_key` 和解析出的配置名称，供前端展示。

## 前端变更

回测页面第一阶段只做运行入口和结果展示：

- 移除账户选择器。
- 移除策略模板选择器。
- 选择单个产品。
- 显示该产品匹配到的 Python 回测配置名称。
- 输入正式起止日期、可选预热起始日期、初始资金、手续费。
- 可选输入 `strategy_params` JSON，用于临时覆盖策略参数。
- 运行回测。
- 展示摘要统计、交易记录、权益曲线、使用的数据源和错误状态。
- 保留历史运行列表和详情选择。

产品配置页面可以先只显示或编辑 `backtest_config_key`。不在第一阶段提供 Strategy DSL 编辑器。

## 持仓和观察池策略提醒

持仓/观察池提醒可以复用同一套 Python 回测配置，但它是回测之外的独立功能。

建议后续新增 `StrategySignalService`：

1. 找到持仓产品和观察池产品。
2. 解析产品的 `backtest_config_key`。
3. 拉取最新 OHLCV 和预热数据。
4. 调用同一个 `prepare_data()`。
5. 用策略规则评估最新一根 K 线。
6. 生成信号，而不是执行交易。

信号语义：

- 未持仓观察池产品：`entry`、`observe`。
- 已持仓产品：`hold`、`add`、`reduce`、`exit`。

这部分不应混进 `BacktestRun`。它应写入独立的信号表或复用现有 `signals` 表的新语义，并支持通知展示。第一阶段回测重构只预留接口，不强制实现提醒。

## 删除与迁移

删除或重写：

- `app/services/backtest_service.py` 中旧的账户组合模拟器。
- 回测 API 中对 `account_id` 和 `template_id` 的解析。
- 前端 `BacktestsPage` 中的账户/模板字段。
- 断言旧账户组合回测行为的测试。

保留并迁移：

- `BacktestRun` 历史记录表。
- 回测列表、详情、创建 API 路由名称。
- 前端历史运行和详情页面结构。

旧 `backtest_runs` 的 `params_json` / `result_json` 和新结构不兼容。前端应能容忍旧记录缺少 `scope.backtest_config_key`、`scope.provider`、`scope.strategy_class` 等字段。

## 测试计划

后端测试：

- `backtest_config_key` 能从产品解析到 Python 注册表配置。
- 未配置回测策略的产品返回校验错误。
- `symbol/market` fallback 能匹配注册表。
- 腾讯 OHLCV provider 可标准化为 Backtesting.py 所需 DataFrame。
- 东方财富基金净值 provider 可转换为 OHLCV。
- `prepare_data()` 在正式日期裁剪前执行。
- Python Strategy 类必须是 `Strategy` 子类。
- `BacktestService.run_backtest()` 可生成可序列化的 summary、equity_curve、trades。
- API 创建接口不再要求 `account_id` 和 `template_id`。

前端测试：

- 回测表单只包含产品、日期、预热日期、初始资金、手续费、参数 JSON。
- 账户和模板选择器已移除。
- 产品选择后能展示匹配到的回测配置名称。
- 创建成功后刷新历史运行列表并选中新运行。
- 失败运行和旧版遗留 JSON 不会导致页面崩溃。

## 第二阶段方向

第一阶段稳定后，再考虑线上配置能力：

- 将 Python 注册表中的策略元信息迁移为 `BacktestStrategy`。
- 将数据源配置迁移为 `BacktestDataSource`。
- 为常见策略提供 JSON DSL。
- 增加结构化策略规则编辑器。
- 支持组合策略，组合多个产品的数据源、信号和仓位规则。

第二阶段不应恢复旧账户模板回测模型，而应基于新的 provider、strategy、runner 边界扩展。
