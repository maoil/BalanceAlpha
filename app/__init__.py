"""
衡策投资系统 (BalanceAlpha)
Flask 应用工厂
"""
import os
import logging
from pathlib import Path

from flask import Flask
from dotenv import load_dotenv
from sqlalchemy import inspect, text

from app.config import config_map


def create_app(config_name: str = None) -> Flask:
    """
    Flask 应用工厂

    Args:
        config_name: 配置名称 (development/production/default)
    """
    # 加载 .env 文件
    load_dotenv()

    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_map.get(config_name, config_map["default"]))

    # 确保数据目录存在
    data_dir = app.config.get("DATA_DIR")
    if data_dir:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        (Path(data_dir) / "imports").mkdir(parents=True, exist_ok=True)

    # 初始化扩展
    _init_extensions(app)

    # 注册蓝图
    _register_blueprints(app)

    # 注册模板上下文
    _register_context_processors(app)

    # 配置日志
    _configure_logging(app)

    return app


def _init_extensions(app: Flask) -> None:
    """初始化 Flask 扩展"""
    from app.extensions import db, migrate, csrf
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # 在应用上下文中创建所有表
    with app.app_context():
        from app.models import (
            Account, Instrument, StrategyTemplate, StrategyAssignment,
            Position, Trade, MarketData, Signal, BacktestRun, SystemLog,
            DcaPlan, DcaOrder,
        )
        db.create_all()
        # NOTE: _ensure_runtime_schema 作为安全网保留，新字段应优先通过
        # flask db migrate / flask db upgrade (Alembic) 管理
        _ensure_runtime_schema(db)

        # 自动创建种子数据（首次启动时）
        _auto_seed(db)


def _register_blueprints(app: Flask) -> None:
    """注册所有蓝图"""
    from app.api import register_api
    from app.views.dashboard import bp as dashboard_bp
    from app.views.backtests import bp as backtests_bp
    from app.views.instruments import bp as instruments_bp
    from app.views.positions import bp as positions_bp
    from app.views.trades import bp as trades_bp
    from app.views.signals import bp as signals_bp
    from app.views.settings import bp as settings_bp
    from app.views.logs import bp as logs_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(backtests_bp, url_prefix="/backtests")
    app.register_blueprint(instruments_bp, url_prefix="/instruments")
    app.register_blueprint(positions_bp, url_prefix="/positions")
    app.register_blueprint(trades_bp, url_prefix="/trades")
    app.register_blueprint(signals_bp, url_prefix="/signals")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(logs_bp, url_prefix="/logs")
    register_api(app)


def _register_context_processors(app: Flask) -> None:
    """注册模板上下文处理器 - 让所有模板可用的变量"""
    from app.utils.constants import (
        SIGNAL_TYPE_LABELS, SIGNAL_TYPE_COLORS,
        InstrumentType, AccountType, InstrumentStatus,
        TradeType, TradeSide, SignalType, SignalStatus,
        LogType, LogLevel,
    )
    from app.utils.helpers import format_pct, format_currency, format_number

    @app.context_processor
    def inject_utils():
        return {
            "SIGNAL_TYPE_LABELS": SIGNAL_TYPE_LABELS,
            "SIGNAL_TYPE_COLORS": SIGNAL_TYPE_COLORS,
            "InstrumentType": InstrumentType,
            "AccountType": AccountType,
            "InstrumentStatus": InstrumentStatus,
            "TradeType": TradeType,
            "TradeSide": TradeSide,
            "SignalType": SignalType,
            "SignalStatus": SignalStatus,
            "LogType": LogType,
            "format_pct": format_pct,
            "format_currency": format_currency,
            "format_number": format_number,
        }


def _configure_logging(app: Flask) -> None:
    """配置日志"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # 确保 app.services 命名空间的日志都输出到控制台
    services_logger = logging.getLogger("app.services")
    services_logger.setLevel(logging.DEBUG)
    # 避免 werkzeug / sqlalchemy 刷屏
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _ensure_runtime_schema(db) -> None:
    """为已有数据库补齐轻量字段，避免 create_all 无法升级旧表结构。"""
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if not table_names:
        return

    if "signals" in table_names:
        columns = {column["name"] for column in inspector.get_columns("signals")}
        statements = []

        if "batch_id" not in columns:
            statements.append(
                text('ALTER TABLE signals ADD COLUMN batch_id VARCHAR(36) DEFAULT ""')
            )
        if "batch_version" not in columns:
            statements.append(
                text("ALTER TABLE signals ADD COLUMN batch_version INTEGER DEFAULT 1")
            )

        if statements:
            with db.engine.begin() as conn:
                for statement in statements:
                    conn.execute(statement)

        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE signals SET batch_version = 1 "
                    "WHERE batch_version IS NULL OR batch_version = 0"
                )
            )

    if "market_data" in table_names:
        columns = {column["name"] for column in inspector.get_columns("market_data")}
        column_definitions = {
            "prev_close": "FLOAT",
            "amount": "FLOAT",
            "turnover_rate": "FLOAT",
            "amplitude": "FLOAT",
            "open_gap_pct": "FLOAT",
            "est_nav": "FLOAT",
            "iopv": "FLOAT",
            "premium_discount_pct": "FLOAT",
            "premium_discount_zscore_20d": "FLOAT",
            "atr14": "FLOAT",
            "volatility_20d": "FLOAT",
            "return_5d": "FLOAT",
            "return_20d": "FLOAT",
            "return_60d": "FLOAT",
            "breakout_high_20d": "FLOAT",
            "breakdown_low_20d": "FLOAT",
            "max_drawdown_120d": "FLOAT",
            "volume_ma20": "FLOAT",
            "volume_ratio_5d": "FLOAT",
        }
        statements = [
            text(f"ALTER TABLE market_data ADD COLUMN {name} {sql_type}")
            for name, sql_type in column_definitions.items()
            if name not in columns
        ]
        if statements:
            with db.engine.begin() as conn:
                for statement in statements:
                    conn.execute(statement)

    if "instruments" in table_names:
        columns = {column["name"] for column in inspector.get_columns("instruments")}
        statements = []
        if "dca_confirm_cycle" not in columns:
            statements.append(
                text("ALTER TABLE instruments ADD COLUMN dca_confirm_cycle INTEGER DEFAULT 1")
            )
        if statements:
            with db.engine.begin() as conn:
                for statement in statements:
                    conn.execute(statement)

    if "trades" in table_names:
        columns = {column["name"] for column in inspector.get_columns("trades")}
        statements = []
        if "source_type" not in columns:
            statements.append(
                text('ALTER TABLE trades ADD COLUMN source_type VARCHAR(30) DEFAULT ""')
            )
        if "source_id" not in columns:
            statements.append(
                text("ALTER TABLE trades ADD COLUMN source_id INTEGER")
            )
        if statements:
            with db.engine.begin() as conn:
                for statement in statements:
                    conn.execute(statement)


def _auto_seed(db) -> None:
    """
    自动创建种子数据（首次启动时）

    如果数据库中没有账户数据，自动创建：
    - 2 个逻辑账户（核心配置 + 战术轮动）
    - 5 个策略模板
    """
    from app.models.account import Account
    from app.models.strategy_template import upsert_default_strategy_templates

    # 如果已有账户，跳过
    if Account.query.count() > 0:
        created_count, updated_count = upsert_default_strategy_templates(db.session)
        logging.info(
            "策略模板同步完成: 新增%s个, 更新%s个",
            created_count,
            updated_count,
        )
        return

    logging.info("首次启动，自动创建种子数据...")

    # 创建账户
    accounts = [
        Account(
            account_code="core",
            account_name="核心配置账户",
            account_type="core",
            description="长期投资、定投、资产配置、月度再平衡",
            status="active",
        ),
        Account(
            account_code="tactical",
            account_name="战术轮动账户",
            account_type="tactical",
            description="主题轮动、趋势交易、主动风控",
            status="active",
        ),
    ]
    db.session.add_all(accounts)
    db.session.commit()

    created_count, updated_count = upsert_default_strategy_templates(db.session)
    logging.info(
        "种子数据创建完成: 2个账户, 策略模板新增%s个, 更新%s个",
        created_count,
        updated_count,
    )
