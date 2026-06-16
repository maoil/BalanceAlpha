# 衡策投资系统（BalanceAlpha）

单用户基金 / ETF / LOF 投资管理与策略决策支持系统，面向"记录交易、维护持仓、抓取行情、生成策略建议、回测验证、定投管理"的完整闭环。

## 项目概览

BalanceAlpha 采用前后端分离架构：

- **后端**：Flask REST API（`/api/v1/`），负责数据管理、策略计算、行情抓取、AI 分析
- **前端**：React 19 + TypeScript + Vite SPA，负责交互展示

核心模块：

- `仪表盘`：账户总览、资产汇总、最近交易、待处理信号
- `产品管理`：基金 / ETF / LOF 基础信息维护，价格与行情抓取
- `交易记录`：手工录入买入、卖出等交易
- `手工基金申购`：场外基金申购赎回订单管理，支持确认后自动生成交易记录
- `持仓管理`：基于交易与行情计算当前持仓、市值、盈亏和权重
- `持仓趋势`：历史持仓变化趋势分析
- `策略建议`：生成核心账户与战术账户的策略信号，支持版本历史与 AI 分析
- `策略绑定`：为产品分配策略模板
- `回测系统`：多策略回测引擎，支持可视化回测结果
- `定投计划`：DCA 定投计划管理与执行
- `参数配置`：策略模板 JSON 参数维护，版本自动递增
- `日志`：系统操作与策略变更日志

## 当前功能

### 1. 双账户策略体系

- `核心配置账户`：长期配置、定投、再平衡
- `战术轮动账户`：趋势交易、止盈止损、主动风控
- API 和前端均按账户类型区分

### 2. 产品管理

- 支持基金、ETF、LOF 等产品录入
- 通过基金代码搜索并自动补全信息
- 抓取单个产品最新价格
- 导入指定天数的历史行情（含技术指标计算）
- 筛选产品状态和默认账户类型
- 支持 DCA 确认周期配置

### 3. 交易与持仓

- 手工录入交易记录
- 手工基金申购/赎回订单（支持确认后自动生成交易）
- 持仓自动刷新最新价格
- 展示持仓市值、浮盈浮亏、仓位权重
- 持仓趋势历史分析

### 4. 策略建议

- 核心账户：基于权重偏离、回撤、趋势、评分生成建议
- 战术账户：基于 MA 趋势、止损、止盈、确认加仓生成建议
- 信号评分机制
- 调仓引导建议
- 查看建议详情和调仓建议 JSON API

### 5. 策略建议版本化

- 每次"生成信号"创建新的 `batch_version`
- 列表默认只显示当前最新版本
- 按产品 + 账户查看历史版本
- 详情页回看同一产品的过往版本记录
- 旧版本待处理信号在新版本生成后自动标记为 `expired`

### 6. 策略绑定与分配

- 为产品指定策略模板
- 支持核心账户 / 战术账户独立绑定

### 7. 回测系统

- 内置多策略回测引擎（vendored backtesting 库）
- 策略包括：CS-AI 动量策略、唐奇安动量策略、基金动量突破策略
- 策略注册中心，支持参数化配置
- 回测结果序列化与可视化
- 独立回测数据提供器

### 8. DCA 定投计划

- 定投计划创建与管理
- 定投订单生成与执行
- 交易日历服务支持

### 9. 参数配置与日志

- 策略模板以 JSON 形式维护
- 修改模板参数后版本号自动递增
- 参数变更写入系统日志
- 策略信号生成记录日志

### 10. AI 分析子层

- LangChain 用于策略建议的 AI 解释与风险分析
- AI 分析不覆盖规则信号，只做解释、风险提示和执行建议补充
- 支持单条信号和批量生成 AI 分析
- 结构化 AI 分析结果（Pydantic schema）
- AI 分析结果独立落表保存

### 11. 市场数据与指标

- 行情数据抓取与存储
- 技术指标计算（ATR、波动率、收益率、突破信号、成交量等）
- 溢折价率与 Z-Score 计算
- 市场情绪分析服务

## 技术栈

### 后端

- `Python 3.11+`
- `Flask 3.1` + REST API（`/api/v1/`）
- `Flask-SQLAlchemy 3.1` + `SQLAlchemy 2.x`
- `Flask-Migrate`（Alembic 数据库迁移）
- `Flask-WTF`（CSRF 保护）
- `SQLite`
- `pandas / numpy`（数据分析与技术指标）
- `akshare / requests`（行情数据抓取）
- `langchain-openai / pydantic`（AI 分析）
- `pytest`（测试）
- `waitress`（可选生产部署）

### 前端

- `React 19` + `TypeScript`
- `Vite 7`（构建工具）
- `Recharts`（图表可视化）
- `Lucide React`（图标库）
- `Vitest`（单元测试）

## 快速开始

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 启动后端 API

```bash
python run.py
```

后端 API 地址：`http://127.0.0.1:5000`

### 3. 安装并启动前端

```bash
cd frontend
npm install
npm run dev
```

前端访问地址：`http://127.0.0.1:5173`

也可以使用辅助脚本启动前端：

```bash
python start_frontend_5173.py
```

### 4. 首次启动自动完成

- 创建数据库文件 `data/balancealpha.db`
- 创建数据目录和导入目录
- 创建全部表结构
- 自动补齐运行时升级字段
- 初始化 2 个账户（核心配置 + 战术轮动）
- 初始化默认策略模板

## 配置说明

应用会自动读取 `.env`。如果没有该文件，使用默认开发配置启动。

可选环境变量示例：

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///data/balancealpha.db
API_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

AI 分析相关：

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-compatible-api/v1
AI_MODEL_NAME=Qwen3.6-Plus
```

说明：

- `FLASK_ENV` 默认是 `development`
- 数据库默认是项目内 SQLite 文件
- `SECRET_KEY` 未配置时使用开发默认值
- `API_CORS_ORIGINS` 控制前端跨域访问白名单
- `OPENAI_BASE_URL` 可选，使用 OpenAI 兼容接口时填写
- 未配置 `OPENAI_API_KEY` 时，AI 分析会生成失败记录并提示缺少密钥

## API 概览

所有 API 均以 `/api/v1/` 为前缀，支持 CORS。主要端点：

| 模块 | 端点前缀 | 说明 |
|---|---|---|
| 健康检查 | `/api/v1/health` | 服务状态 |
| 账户 | `/api/v1/accounts` | 账户管理 |
| 产品 | `/api/v1/instruments` | 产品 CRUD、价格抓取 |
| 交易 | `/api/v1/trades` | 交易记录 |
| 手工基金申购 | `/api/v1/manual-fund-orders` | 场外基金订单 |
| 持仓 | `/api/v1/positions` | 持仓查询与刷新 |
| 策略信号 | `/api/v1/signals` | 策略建议生成与查询 |
| 策略管理 | `/api/v1/strategies` | 策略模板与绑定 |
| 回测 | `/api/v1/backtests` | 回测任务管理 |
| 行情 | `/api/v1/market` | 市场数据 |
| 仪表盘 | `/api/v1/dashboard` | 汇总统计 |
| 配置 | `/api/v1/settings` | 系统配置 |
| 日志 | `/api/v1/logs` | 系统日志 |

## 项目结构

```text
BalanceAlpha/
├── app/
│   ├── __init__.py              # Flask 应用工厂、自动建表、运行时字段补齐
│   ├── config.py                # 配置项（含 CORS 配置）
│   ├── extensions.py            # 扩展初始化（SQLAlchemy / Migrate / CSRF）
│   ├── models/                  # ORM 模型
│   │   ├── account.py           # 账户
│   │   ├── instrument.py        # 产品（基金/ETF/LOF）
│   │   ├── trade.py             # 交易记录
│   │   ├── manual_fund_order.py # 手工基金申购订单
│   │   ├── position.py          # 持仓
│   │   ├── market_data.py       # 行情数据（含技术指标字段）
│   │   ├── signal.py            # 策略信号
│   │   ├── signal_ai_analysis.py# AI 分析结果
│   │   ├── strategy_template.py # 策略模板
│   │   ├── strategy_assignment.py# 策略绑定
│   │   ├── backtest_run.py      # 回测运行记录
│   │   ├── dca_plan.py          # 定投计划
│   │   ├── dca_order.py         # 定投订单
│   │   ├── system_log.py        # 系统日志
│   │   └── base_model.py        # 模型基类
│   ├── services/                # 业务逻辑层
│   │   ├── fund_data_fetcher.py # 行情/基金信息抓取
│   │   ├── market_data_service.py# 行情数据与技术指标服务
│   │   ├── signal_service.py    # 策略信号与版本逻辑
│   │   ├── strategy_signal_service.py # 策略信号生成
│   │   ├── signal_scoring.py    # 信号评分
│   │   ├── position_service.py  # 持仓计算
│   │   ├── position_trend_service.py # 持仓趋势分析
│   │   ├── trade_service.py     # 交易处理
│   │   ├── manual_fund_order_service.py # 手工基金订单服务
│   │   ├── backtest_service.py  # 回测服务
│   │   ├── dca_plan_service.py  # 定投计划服务
│   │   ├── dca_order_service.py # 定投订单服务
│   │   ├── trading_calendar_service.py # 交易日历
│   │   ├── instrument_service.py# 产品服务
│   │   ├── account_service.py   # 账户服务
│   │   ├── dashboard_metrics_service.py # 仪表盘指标
│   │   ├── strategy_performance_service.py # 策略绩效
│   │   ├── market_sentiment_service.py # 市场情绪
│   │   ├── rebalance_guidance_service.py # 调仓引导
│   │   ├── ai_analysis_service.py # AI 分析服务
│   │   ├── langchain_signal_analyzer.py # LangChain 分析器
│   │   ├── ai_prompt_builder.py # AI 提示词构建
│   │   ├── ai_analysis_schema.py# AI 分析结构化 schema
│   │   └── log_service.py       # 日志服务
│   ├── api/                     # REST API 路由
│   │   ├── __init__.py          # 蓝图注册、CORS、健康检查
│   │   ├── accounts.py          # 账户 API
│   │   ├── instruments.py       # 产品 API
│   │   ├── trades.py            # 交易 API
│   │   ├── manual_fund_orders.py# 手工基金订单 API
│   │   ├── positions.py         # 持仓 API
│   │   ├── signals.py           # 策略信号 API
│   │   ├── strategies.py        # 策略管理 API
│   │   ├── backtests.py         # 回测 API
│   │   ├── market.py            # 行情 API
│   │   ├── dashboard.py         # 仪表盘 API
│   │   ├── settings.py          # 配置 API
│   │   ├── logs.py              # 日志 API
│   │   └── responses.py         # 统一响应格式
│   ├── schemas/                 # 序列化层
│   │   └── serializers.py       # 模型序列化器
│   ├── backtesting/             # 回测引擎
│   │   ├── registry.py          # 策略注册中心
│   │   ├── providers.py         # 回测数据提供器
│   │   ├── result_serializer.py # 回测结果序列化
│   │   └── strategies/          # 回测策略实现
│   │       ├── cs_ai_momentum.py    # CS-AI 动量策略
│   │       ├── donchian_momentum.py # 唐奇安动量策略
│   │       └── fund_momentum_breakout.py # 基金动量突破策略
│   ├── vendor/                  # 第三方库本地化
│   │   └── backtesting/         # backtesting.py vendored 版本
│   └── utils/                   # 常量与工具函数
├── frontend/                    # React 前端 SPA
│   ├── src/
│   │   ├── App.tsx              # 路由与主入口
│   │   ├── main.tsx             # 渲染入口
│   │   ├── api/                 # API 客户端与端点定义
│   │   ├── pages/               # 页面组件
│   │   ├── components/          # 公共组件
│   │   ├── hooks.ts             # 自定义 hooks
│   │   ├── types.ts             # TypeScript 类型定义
│   │   └── utils/               # 工具函数
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── tests/                       # 后端测试
├── scripts/                     # 工具脚本
├── data/                        # SQLite 数据文件与导入目录
├── requirements.txt
├── run.py                       # 后端启动入口
├── start_frontend_5173.py       # 前端启动辅助脚本
└── README.md
```

## 常用脚本

```bash
# 启动后端
python run.py

# 启动前端
python start_frontend_5173.py

# 初始化数据库和种子数据
python scripts/init_db.py

# 数据库迁移（Flask-Migrate / Alembic）
flask db migrate -m "描述"
flask db upgrade

# 为旧库补 signals 版本字段
python scripts/migrate_signals_version.py

# 初始化 AI 分析结果表
python scripts/migrate_signal_ai_analysis.py

# 回测相关迁移
python scripts/migrate_backtest.py

# 导入行情数据
python scripts/import_market_data.py

# 批量抓取全部历史行情
python scripts/fetch_all_history.py

# 检查数据库状态
python scripts/check_db.py

# 诊断策略信号
python scripts/diagnose_signals.py

# 修复策略绑定
python scripts/fix_strategy_assignments.py

# 绑定 CS-AI 策略
python scripts/bind_cs_ai_strategy.py

# 查询产品
python scripts/list_instruments.py
python scripts/find_instrument.py

# 恢复持仓快照
python scripts/restore_portfolio_snapshot.py
```

## 开发说明

### 后端依赖安装

```bash
pip install -r requirements.txt
```

### 前端依赖安装

```bash
cd frontend
npm install
```

### 运行测试

后端：

```bash
pytest
```

前端：

```bash
cd frontend
npm test
```

### 代码检查

```bash
# 后端
python -m compileall app

# 前端
cd frontend
npm run lint
```

## 信号版本机制

`signals` 表包含以下版本化字段：

- `batch_id`：同一次生成批次的唯一标识
- `batch_version`：按生成次数递增的版本号

版本规则：

1. 新生成一次信号，版本号加 1
2. 新版本生成完成后，旧的 `pending` 信号统一标记为 `expired`
3. 策略建议列表仅展示最新版本
4. 历史页按版本倒序展示

说明：

- 应用启动时会自动检查并补齐 `signals.batch_id` 和 `signals.batch_version`
- 对于旧数据库，一般不需要手工迁移；如需单独处理，也可使用 `scripts/migrate_signals_version.py`

## AI 分析

AI 分析结果使用独立表 `signal_ai_analysis` 保存，不与 `signals` 主表混用。

### 自动初始化

- 正常启动应用时，`db.create_all()` 会自动创建缺失的 `signal_ai_analysis` 表
- 只要代码已包含 `SignalAIAnalysis` 模型并成功启动，一般不需要额外操作

### 手工迁移旧库

```bash
python scripts/migrate_signal_ai_analysis.py
```

### AI 分析运行前准备

```bash
pip install -r requirements.txt
```

配置环境变量：

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-compatible-api/v1
AI_MODEL_NAME=Qwen3.6-Plus
```

## 已知边界

- 调仓建议详情目前还是结构化占位，尚未实现完整分步买卖金额计算
- 当前默认数据库为 SQLite，更适合单机个人使用
- 行情抓取依赖外部数据源，稳定性受网络和第三方接口影响
- 回测策略结果仅供参考，不构成投资建议

## 后续可扩展方向

- 完善调仓建议的分步执行方案
- 增加更多回测策略与绩效分析
- 增加更多风险指标和统计报表
- 补充更多自动化测试覆盖
- 提供导出报表或快照能力
- 支持更多数据源接入
