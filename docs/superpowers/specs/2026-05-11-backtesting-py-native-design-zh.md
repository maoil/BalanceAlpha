# Backtesting.py 原生回测重构设计

## 背景

BalanceAlpha 目前有一个自定义回测服务，通过账户、产品和策略模板的组合来模拟账户级别的组合投资行为。本次设计目标是用 `backtesting.py` 原生的单产品工作流来替代该模型。

需要内置（vendor）的源代码实现位于：

`C:\Users\guangxin.yang\BalanceAlpha\backtesting.py-master\backtesting.py-master\backtesting`

脚本 `your_script.py` 是期望执行模型的参考实现：

1. 从远程数据源获取日线 OHLCV 数据。
2. 在预热数据窗口上计算衍生指标。
3. 将准备好的数据裁剪到正式回测起始日期。
4. 执行 `Backtest(data, StrategyClass, ...)`。
5. 持久化统计数据、权益曲线、交易记录，以及可选的 HTML 图表。

## 目标

- 移除旧的账户组合回测语义。
- 将 `backtesting.py` 引擎内置到 BalanceAlpha 中，以便本地适配修改。
- 使用 `Backtest` 和 `Strategy` 以单产品 OHLCV 模拟方式运行回测。
- 允许每个产品配置一个默认回测策略。
- 优先使用可配置的策略 DSL 来定义常见策略。
- 保留基于 Python 文件的 `Strategy` 类作为高级回退方案。
- 通过可配置的数据源 URL 获取远程 OHLCV 数据，支持优先级回退。
- 保留历史 `BacktestRun` 记录，并暴露列表、创建和详情 API。
- 为未来的组合投资策略保留设计路径，但不重新引入旧的账户模板模型。

## 非目标

- 不保留旧的基于账户、模板和分配的回测行为。
- 不执行来自不可信用户的任意 Python 代码。
- 第一版不构建完整的在线 Python IDE 来编辑策略代码。
- 不要求每次回测都依赖本地 `MarketData` 记录。远程数据源是主要数据来源。

## 架构

新的回测层有五个边界：

1. `app/vendor/backtesting`：内置的 `backtesting.py` 包。
2. 数据提供方（Data Providers）：获取并标准化远程 OHLCV 数据。
3. 策略注册表（Strategy Registry）：解析产品所配置的策略。
4. 策略编译器（Strategy Compiler）：将 DSL 策略规格转换为 `Strategy` 子类。
5. 回测执行器（Backtest Runner）：执行 `Backtest`，序列化结果，并持久化 `BacktestRun`。

业务代码应该只调用 BalanceAlpha 的封装服务。API 处理器和前端代码不应直接导入内置引擎的内部模块。

## 数据提供方

产品可以有一个或多个回测数据源。第一版应支持优先级回退：

- 按优先级升序尝试已启用的数据源。
- 应用各数据源特定的 URL 模板和解析适配器。
- 根据数据源配置对瞬时故障进行重试。
- 在第一个返回非空标准化 OHLCV 数据的数据源处停止。
- 如果所有数据源都失败，抛出验证错误。

建议的 `BacktestDataSource` 字段：

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

`url_template` 可以包含占位符，例如 `{symbol}`、`{start}`、`{end}`、`{market}` 和 `{adjustment}`。数据源适配器负责最终的请求格式和响应解析。

数据源适配器以代码形式实现，不作为任意数据库代码存储。初始数据源类型：

- `tencent_daily_ohlcv`：股票或 ETF 日线 K 线数据，类似 `your_script.py` 中的 `fetch_daily_ohlcv()`。
- `eastmoney_fund_nav`：基金净值数据，通过将 `Open`、`High`、`Low`、`Close` 统一设为净值来转换为 OHLCV 格式。

标准化后的 DataFrame 必须包含：

- 按升序排列的 `DatetimeIndex`。
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`

允许包含额外列，策略可以使用这些列。

远程数据后续可以缓存到 `MarketData` 中，但第一版设计将远程数据源作为回测的数据真实来源。

## 策略模型

每个产品指向一个默认策略。策略配置使用两种模式。

### 配置策略（Config Strategy）

默认模式是存储在数据库中的 JSON 策略规格。它描述了指标、入场规则、出场规则、仓位管理和回测执行参数。

建议的 `BacktestStrategy` 字段：

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

`mode = "config"` 表示 `spec_json` 会被编译为一个生成的 `Strategy` 子类。

唐奇安动量策略的示例规格：

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

编译器在正式日期裁剪之前预先计算指标，然后创建一个 `Strategy` 类，其 `init()` 方法通过 `self.I(...)` 注册指标，`next()` 方法应用入场和出场规则树。

第一版 DSL 支持范围：

- 指标：`sma`、`ema`、`rolling_max`、`rolling_min`、`pct_change`、`rsi`。
- 运算符：`>`、`>=`、`<`、`<=`、`==`、`cross_above`（上穿）、`cross_below`（下穿）。
- 逻辑组合：`all`（全部满足）、`any`（任一满足）、嵌套分组。
- 引用：当前列或指标值，加上滞后语法如 `HH10[-2]`。
- 方向：`long_only`（仅做多）。
- 仓位大小：`all_available`（全仓）、固定金额、权益百分比。
- 回测参数：`exclusive_orders`、`finalize_trades`、`trade_on_close`、`commission` 和 `cash`。

### Python 模块策略（Python Module Strategy）

高级策略可以用已提交的 Python 文件实现。数据库中只存储引用和参数。

`mode = "python_module"` 时 `spec_json` 中的字段：

```json
{
  "module_path": "app.backtest_strategies.donchian_custom",
  "class_name": "DonchianMomentumChaser",
  "prepare_func_name": "prepare_data"
}
```

被引用的类必须继承内置的 `Strategy`。如果指定了 `prepare_func_name`，执行器会在正式日期裁剪之前调用该函数。

这种模式是在策略无法用 JSON DSL 清晰表达时的回退方案。它将复杂代码保留在 git 中，支持正常的 IDE 开发流程，避免在数据库中存储大段 Python 模块。

## 配置管理

第一版应包含最小化的策略和数据源配置 CRUD 支持，避免将策略硬编码到数据库迁移中：

- 列表、创建、更新和停用 `BacktestStrategy` 记录。
- 列表、创建、更新和停用产品的 `BacktestDataSource` 记录。
- 为产品指定默认策略。
- 编辑产品级别的策略参数覆盖。

前端可以先用 JSON 文本框来编辑 `spec_json`、`default_params_json`、`default_backtest_config_json` 和 `backtest_params_json`。在 DSL 格式稳定后，再增加结构化的规则构建器 UI。

## 产品绑定

在 `Instrument` 上添加策略绑定字段：

- `backtest_strategy_id`
- `backtest_params_json`

`backtest_params_json` 覆盖该产品的策略默认值。产品级别的参数在 `BacktestStrategy.default_params_json` 之后合并。

每个产品还应有一条或多条 `BacktestDataSource` 记录。

## BacktestRun 模型

保留历史运行记录表，但将其语义从账户组合运行改为单产品策略运行。

建议字段：

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

`template_id` 不再属于回测模型。

## 执行流程

`BacktestService.run_backtest()` 应该：

1. 验证 `instrument_id`、`start_date`、`end_date` 和 `initial_capital`。
2. 解析产品的活跃 `BacktestStrategy`。
3. 按优先级解析已启用的 `BacktestDataSource` 记录。
4. 计算 `warmup_start_date`。如果已明确指定则使用该值，否则根据策略预热需求推导，或使用保守默认值（如 250 个交易日）。
5. 从第一个成功的数据源获取 `warmup_start_date` 至 `end_date` 的原始 OHLCV 数据。
6. 标准化并验证 DataFrame。
7. 解析或编译策略：
   - Config 模式：将 `spec_json` 编译为生成的 `Strategy` 子类并计算指标列。
   - Python 模块模式：导入模块，调用可选的 `prepare_data`，加载 `class_name`。
8. 将准备好的数据裁剪到 `start_date:end_date`。
9. 执行：

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

10. 序列化：
    - 标量统计指标。
    - `_equity_curve`（权益曲线）。
    - `_trades`（交易记录）。
    - 数据源元信息。
    - 策略元信息和参数。
    - 可选的图表 HTML 路径（如已生成）。
11. 标记运行状态为已完成或失败，并持久化结果 JSON。

## 结果 JSON 结构

存储的结果应当稳定，便于前端展示：

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

具体的统计键名可以与 `backtesting.py` 保持一致，但 `summary` 对象应使用 BalanceAlpha 风格的 snake_case 键名。

## API 变更

保留现有端点：

- `GET /api/v1/backtests`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/<id>`

创建请求的 payload 改为：

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

从回测创建接口中移除 `account_id` 和 `template_id`。

在本次重构中新增或扩展产品配置 API，使前端可以管理：

- 产品的默认回测策略。
- 产品的数据源。
- 产品级别的策略参数覆盖。

## 前端变更

回测页面应该：

- 移除账户和策略模板选择器。
- 选择单个产品。
- 显示产品所配置的策略名称。
- 接受日期范围、可选的预热起始日期、初始资金和手续费。
- 执行回测。
- 展示摘要统计、交易记录、权益曲线、使用的数据源和错误状态。
- 保留历史运行列表和详情选择。

第一版可以展示结果 JSON 或摘要表格。在后端结果格式稳定后，再添加丰富的图表功能。

## 删除与迁移

删除或替换：

- `app/services/backtest_service.py` 中的自定义账户组合模拟。
- 回测 API 中对 `account_id` 和 `template_id` 的解析。
- 前端 `BacktestsPage` 上的账户/模板字段。
- 断言账户组合行为的测试用例。

保留并迁移：

- `BacktestRun` 作为历史记录存储。
- 回测的列表/详情/创建 API 路由名称。
- 基本的前端历史/详情页面结构。

旧的 `backtest_runs` 记录可能变得不兼容，因为它们的 `params_json` 和 `result_json` 是由旧模型生成的。第一次迁移可以保留这些记录在表中，但 UI 应能容忍旧记录缺少新的 `scope.strategy_id` 和 `scope.instrument_id` 字段。

## 安全性

第一版假设是受信任的本地单用户环境。

Config 模式策略不执行用户 Python 代码，应优先用于日常在线配置。

Python 模块策略仅执行已提交的本地代码。第一版不支持在数据库中存储任意 Python 代码。

如果 BalanceAlpha 未来支持不受信任的用户，策略执行必须迁移到隔离的进程或容器中，并设置资源限制和受限的文件系统/网络策略。

## 测试计划

后端测试：

- 数据源回退：在某个数据源失败后使用下一个已启用的数据源。
- 腾讯风格的 OHLCV 数据能标准化为所需的 DataFrame 列。
- 东方财富净值数据能标准化为 OHLCV 格式。
- 未配置策略的产品返回验证错误。
- Config 模式的唐奇安策略能编译并运行。
- Python 模块策略仅加载合法的 `Strategy` 子类。
- 预热数据在裁剪正式范围之前用于指标计算。
- 运行结果存储可序列化的摘要、权益曲线和交易记录。
- API 创建接口不再要求 `account_id` 或 `template_id`。

前端测试：

- 回测表单包含产品、日期、预热日期、初始资金和手续费。
- 账户和模板选择器已移除。
- 成功创建后刷新历史运行列表并选中新创建的运行。
- 摘要展示能容忍失败的运行和旧版遗留运行的 JSON 格式。

## 未来组合投资策略路径

未来的组合策略不应复活旧的账户模板模拟器。取而代之，添加一个独立的组合投资策略层，组合使用：

- 多个产品的数据源。
- 多个产品的策略规格或信号。
- 组合级别的资产配置和再平衡规则。

该层仍然可以使用相同的数据源注册表、策略 DSL、结果序列化和运行历史模型，但应该以新的策略模式或组合运行类型来表示，并具有明确的接口。
