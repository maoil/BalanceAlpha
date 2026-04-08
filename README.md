# 衡策投资系统 (BalanceAlpha)

单用户基金/ETF/LOF 投资管理与策略决策支持系统。

## 功能特性

- **双账户隔离**：核心配置账户（长期）+ 战术轮动账户（短期）
- **产品管理**：支持基金、ETF、LOF，搜索自动填充信息
- **持仓管理**：交易驱动自动计算，实时刷新市场价格
- **在线数据抓取**：自动从东方财富/天天基金获取净值和行情
- **策略信号**：核心账户评分驱动 + 战术账户趋势驱动
- **回测验证**：历史数据验证策略表现（开发中）
- **操作日志**：所有变更可追溯

## 技术栈

- Python 3.11+
- Flask 3.x + Jinja2 + Bootstrap 5
- SQLAlchemy 2.x + SQLite
- akshare + 东方财富接口（行情数据）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动应用

```bash
python run.py
```

首次启动会自动：
- 创建 SQLite 数据库 (`data/balancealpha.db`)
- 初始化 2 个逻辑账户（核心配置 + 战术轮动）
- 初始化 4 个策略模板

### 3. 访问系统

浏览器打开 http://127.0.0.1:5000

## 使用流程

1. **产品管理** → 新增产品（搜索基金代码自动填充）
2. **产品管理** → 点击 ☁ 按钮获取最新报价 / 📋 抓取历史数据
3. **交易记录** → 录入买入/卖出交易
4. **持仓管理** → 自动显示持仓，刷新市场价格
5. **策略建议** → 点击"生成信号"获取操作建议
6. **参数配置** → 修改策略模板参数

## 项目结构

```
BalanceAlpha/
├── app/
│   ├── __init__.py          # Flask app 工厂 (自动种子数据)
│   ├── config.py            # 配置
│   ├── extensions.py        # SQLAlchemy 扩展
│   ├── models/              # 10张表 ORM 模型
│   ├── services/            # 业务逻辑层
│   │   ├── fund_data_fetcher.py  # 基金数据抓取 ★
│   │   ├── signal_service.py     # 策略信号引擎
│   │   └── ...
│   ├── views/               # Flask 路由
│   ├── templates/           # Jinja2 页面
│   ├── static/              # CSS/JS
│   └── utils/               # 常量/枚举/工具
├── data/                    # SQLite 数据库
├── scripts/                 # 初始化/导入脚本
├── requirements.txt
├── run.py                   # 启动入口
└── README.md
```

## 配置

复制 `.env.example` 为 `.env`，按需修改：

```
FLASK_APP=run.py
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key
```
