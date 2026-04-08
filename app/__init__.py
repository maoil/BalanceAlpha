"""
衡策投资系统 (BalanceAlpha)
Flask 应用工厂
"""
import os
import logging
from pathlib import Path

from flask import Flask
from dotenv import load_dotenv

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
    from app.extensions import db
    db.init_app(app)

    # 在应用上下文中创建所有表
    with app.app_context():
        from app.models import (
            Account, Instrument, StrategyTemplate, StrategyAssignment,
            Position, Trade, MarketData, Signal, BacktestRun, SystemLog,
        )
        db.create_all()

        # 自动创建种子数据（首次启动时）
        _auto_seed(db)


def _register_blueprints(app: Flask) -> None:
    """注册所有蓝图"""
    from app.views.dashboard import bp as dashboard_bp
    from app.views.instruments import bp as instruments_bp
    from app.views.positions import bp as positions_bp
    from app.views.trades import bp as trades_bp
    from app.views.signals import bp as signals_bp
    from app.views.settings import bp as settings_bp
    from app.views.logs import bp as logs_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(instruments_bp, url_prefix="/instruments")
    app.register_blueprint(positions_bp, url_prefix="/positions")
    app.register_blueprint(trades_bp, url_prefix="/trades")
    app.register_blueprint(signals_bp, url_prefix="/signals")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(logs_bp, url_prefix="/logs")


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
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _auto_seed(db) -> None:
    """
    自动创建种子数据（首次启动时）

    如果数据库中没有账户数据，自动创建：
    - 2 个逻辑账户（核心配置 + 战术轮动）
    - 4 个策略模板
    """
    import json
    from app.models.account import Account
    from app.models.strategy_template import StrategyTemplate

    # 如果已有账户，跳过
    if Account.query.count() > 0:
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

    # 创建策略模板
    templates = [
        StrategyTemplate(
            template_code="core_index_template",
            template_name="核心宽基指数策略",
            account_type="core",
            description="适用于标普500、纳指100等宽基指数基金/ETF",
            config_json=json.dumps({
                "target_weight_lower": 0.15,
                "target_weight_upper": 0.30,
                "rebalance_threshold": 0.20,
                "score_threshold_buy": 70,
                "score_threshold_hold": 55,
                "dca_allowed": True,
            }, ensure_ascii=False),
            version="1.0",
            status="active",
        ),
        StrategyTemplate(
            template_code="core_active_fund_template",
            template_name="核心主动基金策略",
            account_type="core",
            description="适用于全球成长型主动管理基金",
            config_json=json.dumps({
                "target_weight_lower": 0.10,
                "target_weight_upper": 0.25,
                "rebalance_threshold": 0.20,
                "dca_allowed": True,
                "dca_frequency": "monthly",
            }, ensure_ascii=False),
            version="1.0",
            status="active",
        ),
        StrategyTemplate(
            template_code="gold_hedge_template",
            template_name="黄金对冲策略",
            account_type="core",
            description="适用于黄金ETF，作为组合平衡器",
            config_json=json.dumps({
                "target_weight_lower": 0.05,
                "target_weight_upper": 0.15,
                "rebalance_threshold": 0.20,
                "allow_active_add": False,
            }, ensure_ascii=False),
            version="1.0",
            status="active",
        ),
        StrategyTemplate(
            template_code="tactical_theme_template",
            template_name="战术主题轮动策略",
            account_type="tactical",
            description="适用于AI、软件、半导体等主题资产",
            config_json=json.dumps({
                "ma_short": 20,
                "ma_long": 60,
                "initial_position_pct": 0.30,
                "add_confirm_pct": 0.04,
                "stop_loss_pct": -0.08,
                "stop_loss_clear_pct": -0.10,
                "take_profit_pct_1": 0.15,
                "take_profit_pct_2": 0.25,
                "trailing_stop_pct": -0.08,
            }, ensure_ascii=False),
            version="1.0",
            status="active",
        ),
    ]
    db.session.add_all(templates)
    db.session.commit()

    logging.info("种子数据创建完成: 2个账户, 4个策略模板")
