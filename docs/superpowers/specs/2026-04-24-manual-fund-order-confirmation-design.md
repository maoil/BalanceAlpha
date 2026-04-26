# 场外基金手工录入待确认与持仓确认设计

- 日期：2026-04-24
- 主题：场外基金手工买入录入、待确认、手工入仓与刷新报价自动兜底
- 状态：设计完成，待用户评审

## 1. 背景

当前系统的手工交易录入接口会直接创建 `trade`，随后立即调用 `PositionService.update_from_trade()` 更新持仓。这个模型适用于场内 ETF、LOF 等“录入即成交”的产品，但不适用于场外基金手工申购：

- 录入当日通常拿不到当日最终净值。
- 录入当日无法确定最终确认份额。
- 场外基金买入应按产品确认周期 `T+1` 或 `T+2`，并按交易所工作日计算确认日。
- 只有达到确认条件且净值可用后，才能正式入仓并计算份额、成本和持仓。

因此，本次设计将场外基金手工买入拆分为两个阶段：

1. 录入阶段：创建一笔“待确认单”，记录申购事实，但不更新持仓。
2. 确认阶段：在达到确认条件且净值可用时，计算份额并生成正式 `trade`，再更新持仓。

## 2. 目标与非目标

### 2.1 目标

- 只处理场外基金手工买入录入，即 `instrument_type = fund` 且 `trade_mode = eod_nav`。
- 根据产品配置判断确认周期为 `T+1` 或 `T+2`。
- 手工录入时先创建待确认记录，不直接创建正式成交记录，不直接更新持仓。
- 点击“录入持仓”时，如果已达到确认条件且净值可用，则正式入仓。
- 点击“刷新报价”时，如果已达到确认条件，则自动兜底入仓。
- 确认入仓时使用净值和金额计算份额：

```text
confirm_quantity = (amount - fee) / confirm_nav
```

- 正式入仓后，沿用现有 `Trade` 和 `Position` 逻辑更新持仓、成本和权重。

### 2.2 非目标

- 不处理场外基金赎回。
- 不处理场内 ETF、LOF、现金类产品。
- 不接入真实券商或基金销售平台的下单接口。
- 不在本次设计中重构现有 `dca_orders` 为通用订单模型。

## 3. 适用范围与业务规则

### 3.1 适用范围

- 仅当产品为场外基金手工买入时走本流程。
- 场内产品继续沿用现有手工交易录入逻辑：直接创建正式 `trade` 并更新持仓。

### 3.2 确认周期规则

- 确认周期来源于产品配置，沿用现有字段 `instruments.dca_confirm_cycle`。
- 只允许 `1` 或 `2`，分别表示 `T+1`、`T+2`。
- 确认日通过 `TradingCalendarService.add_trading_days(order_date, confirm_cycle)` 计算。
- 这里的 `T` 按交易所工作日计算，周末和节假日不计入。

### 3.3 可录入持仓条件

达到录入要求定义为同时满足以下条件：

- `today >= expected_confirm_date`
- 净值接口返回了可用净值
- `nav_date >= expected_confirm_date`
- 净值 `confirm_nav > 0`
- 待确认单仍为 `pending`，且尚未存在 `linked_trade_id`

说明：

- `expected_confirm_date` 是最早可确认日，不代表当天一定有净值。
- 真正的入仓日期以实际拿到可用净值的日期为准，即 `actual_confirm_date = nav_date`。

## 4. 数据模型设计

## 4.1 新增表 `manual_fund_orders`

该表只服务于场外基金手工买入录入，不替代 `trades`，也不替代 `dca_orders`。

建议字段：

- `id`
- `account_id`
- `instrument_id`
- `order_date`
- `expected_confirm_date`
- `actual_confirm_date`
- `amount`
- `fee`
- `confirm_nav`
- `confirm_quantity`
- `quote_date_used`
- `status`：`pending / confirmed / cancelled`
- `linked_trade_id`
- `created_at`
- `updated_at`

建议约束：

- `amount > 0`
- `fee >= 0`
- `linked_trade_id` 唯一，防止一笔待确认单映射多笔正式交易
- `(account_id, instrument_id, order_date, amount, status)` 不做强唯一约束，避免误伤用户同日多次申购场景
- 增加 `(status, expected_confirm_date)` 索引用于扫描待确认单

## 4.2 现有表职责保持不变

- `trades`：只表示“已确认成交事实”
- `positions`：只表示已确认持仓事实
- `dca_orders`：继续服务定投确认，不在本次中抽象合并

## 5. 服务边界设计

## 5.1 `TradeService`

保留现有职责：

- 创建正式成交记录
- 创建正式成交后立即更新持仓

变更原则：

- 不再让场外基金手工买入直接走 `TradeService.create()` 的“即成交”路径
- 场外基金手工买入先创建 `manual_fund_order`

## 5.2 新增 `ManualFundOrderService`

新增专门服务，建议负责以下职责：

- 创建待确认单
- 判断一笔待确认单是否达到确认条件
- 拉取确认净值
- 确认待确认单并生成正式 `trade`
- 提供手工确认入口与批量自动确认入口

建议方法：

- `create_pending_order(data)`
- `get_pending_orders_ready_for_confirmation(run_date=None)`
- `confirm_order(order_id)`
- `confirm_due_orders(run_date=None)`

## 5.3 `TradingCalendarService`

继续负责：

- 是否为交易日
- 交易日顺延
- `T+1/T+2` 的确认日计算

本次不引入新的日历规则实现。

## 5.4 `FundDataFetcher`

继续负责：

- 拉取场外基金净值与净值日期

本次确认逻辑沿用 `get_realtime_nav()` 作为净值入口。

## 6. 接口与流程设计

## 6.1 手工交易录入接口

入口：现有 `POST /api/v1/trades`

处理规则：

- 如果产品不是场外基金手工买入，则维持现有逻辑。
- 如果产品是场外基金手工买入，则不直接创建 `trade`，改为创建 `manual_fund_order`。

待确认单创建规则：

- `order_date = 用户录入日期`
- `expected_confirm_date = add_trading_days(order_date, dca_confirm_cycle)`
- `amount = 录入金额`
- `fee = 录入手续费，默认 0`
- `status = pending`

接口返回建议：

- 返回待确认单信息
- 返回当前状态为 `pending`
- 明确告知该笔记录尚未入仓

## 6.2 手工“录入持仓”入口

建议新增接口：

`POST /api/v1/manual-fund-orders/<order_id>/confirm`

处理规则：

1. 读取待确认单
2. 判断是否已达到确认条件
3. 拉取净值
4. 如果未到确认条件或净值不可用，则返回业务错误，不入仓
5. 如果满足条件，则进入确认事务

确认事务中执行：

1. 计算 `confirm_quantity = (amount - fee) / confirm_nav`
2. 创建正式 `trade`
3. 调用 `PositionService.update_from_trade()` 更新持仓
4. 回写 `manual_fund_order`：
   - `status = confirmed`
   - `actual_confirm_date = nav_date`
   - `confirm_nav = nav`
   - `confirm_quantity = quantity`
   - `quote_date_used = nav_date`
   - `linked_trade_id = trade.id`

## 6.3 刷新报价自动兜底

入口：现有刷新报价流程

处理原则：

- 刷新报价仍然先处理报价更新
- 报价更新完成后，增加一步扫描 `manual_fund_orders.status = pending` 的待确认单
- 对所有满足条件的待确认单调用同一套确认服务

这样形成两种触发方式：

- 主路径：用户点击“录入持仓”
- 兜底路径：用户点击“刷新报价”后，系统自动确认可入仓单据

## 7. 正式成交生成规则

确认成功后生成一笔正式买入交易，建议口径如下：

- `trade_type = subscribe` 或新增更明确的手工基金买入类型
- `side = buy`
- `trade_date = actual_confirm_date`
- `price = confirm_nav`
- `quantity = confirm_quantity`
- `amount = original amount`
- `fee = fee`
- `reason_code = manual_fund_confirmed`
- `source_type = manual_fund_order`
- `source_id = manual_fund_order.id`

推荐做法：

- 优先保持现有枚举兼容，使用 `trade_type = subscribe`
- 用 `source_type/source_id/reason_code` 区分“手工场外基金确认入仓”

这样可以减少枚举改动面，同时保留来源追踪能力。

## 8. 幂等与异常处理

### 8.1 幂等要求

- 同一笔 `manual_fund_order` 只能确认一次
- 如果 `linked_trade_id` 已存在，则手工确认和自动确认都必须直接跳过
- 正式 `trade` 创建与待确认单状态更新必须在同一事务中完成
- 手工点击“录入持仓”和刷新报价自动确认必须共用同一个确认方法，不能各自实现一套逻辑

### 8.2 异常处理规则

- 未到 `expected_confirm_date`：返回“未到可录入时点”
- 净值不可用：返回“净值未就绪”
- `nav_date < expected_confirm_date`：继续保持 `pending`
- `confirm_nav <= 0`：记录错误并保持 `pending`
- `confirm_quantity <= 0`：记录错误并保持 `pending`
- 某一笔自动确认失败：不影响其他产品报价刷新和其他待确认单扫描

## 9. 流程时序

## 9.1 录入阶段

1. 用户录入场外基金手工买入
2. 系统识别产品为 `fund + eod_nav`
3. 系统根据 `dca_confirm_cycle` 计算 `expected_confirm_date`
4. 系统创建 `manual_fund_order(status=pending)`
5. 系统不创建正式 `trade`
6. 系统不更新 `position`

## 9.2 手工确认阶段

1. 用户点击“录入持仓”
2. 系统检查待确认单是否达到确认条件
3. 系统拉取净值
4. 条件不满足则直接返回
5. 条件满足则生成正式 `trade` 并更新 `position`
6. 系统将待确认单标记为 `confirmed`

## 9.3 自动兜底阶段

1. 用户点击“刷新报价”
2. 系统完成报价刷新
3. 系统扫描所有满足条件的 `pending manual_fund_orders`
4. 系统逐笔调用确认逻辑
5. 满足条件的单据自动入仓

## 10. 对现有代码的影响

直接影响模块：

- `app/api/trades.py`
- `app/services/trade_service.py`
- `app/services/fund_data_fetcher.py`
- `app/services/trading_calendar_service.py`
- `app/services/position_service.py`
- `app/models/trade.py`

建议新增模块：

- `app/models/manual_fund_order.py`
- `app/services/manual_fund_order_service.py`
- 与之对应的序列化逻辑和 API 路由

改造原则：

- 不破坏现有场内产品手工录入路径
- 不破坏现有定投确认路径
- 不让 `TradeService` 承担待确认单建模职责
- 不让 `PositionService` 感知待确认状态

## 11. 测试范围

至少覆盖以下场景：

1. 场外基金买入录入后只生成 `pending manual_fund_order`
2. 场内产品录入仍保持原有逻辑
3. `T+1` 和 `T+2` 的 `expected_confirm_date` 按交易日计算正确
4. 到了 `expected_confirm_date` 但净值不可用时，不允许入仓
5. 到了 `expected_confirm_date` 但 `nav_date` 早于预期确认日时，不允许入仓
6. 手工点击“录入持仓”且条件满足时，正确生成正式 `trade` 并更新 `position`
7. 点击“刷新报价”时，满足条件的待确认单可自动入仓
8. 同一笔待确认单重复点击或重复刷新，不会重复生成交易
9. 手续费为 `0` 和非 `0` 时，份额计算正确
10. 事务中任一环节失败时，不会出现“已生成 trade 但待确认单仍是 pending”的半完成状态

## 12. 最终结论

本次设计采用“新增手工场外基金待确认单”的方案，而不是扩展现有 `trades` 表承载待确认状态。原因是：

- `Trade` 继续只表示已确认成交，语义清晰
- `Position` 继续只表示已确认持仓，避免提前扭曲成本和收益
- 手工点击“录入持仓”和“刷新报价自动兜底”可以共用一套确认服务，幂等和事务边界明确
- 对现有场内交易和定投逻辑影响最小

该方案可以满足以下业务目标：

- 录入时不需要当日净值
- 根据 `T+1/T+2` 和交易日规则控制何时允许入仓
- 入仓时以实际可用净值计算份额
- 用户既可以主动点击“录入持仓”，也可以通过“刷新报价”触发自动兜底入仓
