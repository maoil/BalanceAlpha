"""
策略模板模型与默认模板定义
"""
import json
from copy import deepcopy
from datetime import datetime

from app.extensions import db


class StrategyTemplate(db.Model):
    __tablename__ = "strategy_templates"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_code = db.Column(db.String(100), unique=True, nullable=False, comment="模板编码")
    template_name = db.Column(db.String(200), nullable=False, comment="模板名称")
    account_type = db.Column(db.String(20), nullable=False, comment="适用账户类型: core/tactical")
    description = db.Column(db.Text, default="", comment="描述")
    config_json = db.Column(db.Text, default="{}", comment="默认参数JSON")
    version = db.Column(db.String(20), default="1.0", comment="版本号")
    status = db.Column(db.String(20), default="active", comment="状态: active/disabled")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关系
    assignments = db.relationship("StrategyAssignment", backref="template", lazy="dynamic")
    backtest_runs = db.relationship("BacktestRun", backref="template", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<StrategyTemplate {self.template_code}>"


DEFAULT_STRATEGY_TEMPLATE_SPECS = [
    {
        "template_code": "core_index_template",
        "template_name": "核心宽基指数策略",
        "account_type": "core",
        "description": "适用于纳指100ETF、标普500LOF等核心宽基指数产品，执行区间仓位管理与现金缓冲",
        "config": {
            "target_weight_lower": 0.18,
            "target_weight_upper": 0.22,
            "instrument_weight_ranges": {
                "513110": {
                    "target_weight_lower": 0.20,
                    "target_weight_upper": 0.24,
                    "role": "进攻主引擎",
                },
                "161125": {
                    "target_weight_lower": 0.16,
                    "target_weight_upper": 0.20,
                    "role": "核心Beta底仓",
                },
            },
            "group_target_weight_lower": 0.38,
            "group_target_weight_upper": 0.42,
            "cash_buffer_lower": 0.05,
            "cash_buffer_upper": 0.10,
            "rebalance_mode": "range",
            "rebalance_to_midpoint": True,
            "score_threshold_buy": 70,
            "score_threshold_hold": 55,
            "dca_allowed": True,
            "score_role": "allocation_priority",
        },
        "version": "2.1",
        "status": "active",
    },
    {
        "template_code": "core_active_fund_template",
        "template_name": "核心主动基金策略",
        "account_type": "core",
        "description": "适用于全球成长型主动管理基金，执行受控增强与逻辑止损",
        "config": {
            "target_weight_lower": 0.10,
            "target_weight_upper": 0.12,
            "group_target_weight_lower": 0.20,
            "group_target_weight_upper": 0.24,
            "cash_buffer_lower": 0.05,
            "cash_buffer_upper": 0.10,
            "rebalance_mode": "range",
            "dca_allowed": True,
            "dca_frequency": "monthly",
            "logic_stop_loss": "alpha_failure",
            "benchmark_underperform_quarters": 2,
            "manager_change_alert": True,
            "style_drift_alert": True,
        },
        "version": "2.1",
        "status": "active",
    },
    {
        "template_code": "gold_hedge_template",
        "template_name": "黄金对冲策略",
        "account_type": "core",
        "description": "适用于黄金ETF，作为组合缓冲器与尾部风险对冲仓",
        "config": {
            "target_weight_lower": 0.13,
            "target_weight_upper": 0.15,
            "target_weight_mid": 0.14,
            "cash_buffer_lower": 0.05,
            "cash_buffer_upper": 0.10,
            "rebalance_mode": "range",
            "allow_active_add": False,
            "allow_passive_add": True,
            "hedge_only": True,
            "priority_reduce_on_hedge_failure": True,
        },
        "version": "2.1",
        "status": "active",
    },
    {
        "template_code": "dividend_low_vol_template",
        "template_name": "红利低波策略",
        "account_type": "core",
        "description": "适用于红利低波类产品，作为防守型权益仓参与核心配置",
        "config": {
            "target_weight_lower": 0.13,
            "target_weight_upper": 0.15,
            "target_weight_mid": 0.14,
            "cash_buffer_lower": 0.05,
            "cash_buffer_upper": 0.10,
            "rebalance_mode": "range",
            "dca_allowed": True,
            "allocation_priority": "low",
            "tracking_error_alert": True,
            "index_method_change_alert": True,
        },
        "version": "2.1",
        "status": "active",
    },
    {
        "template_code": "tactical_theme_template",
        "template_name": "战术动能趋势策略",
        "account_type": "tactical",
        "description": "适用于AI、软件、半导体等高弹性主题资产，执行分层止损、分层止盈与盈利保护",
        "config": {
            "ma_short": 20,
            "ma_long": 60,
            "initial_position_pct": 0.40,
            "add_confirm_pct": 0.05,
            "add_position_pct": 0.30,
            "entry_rs_threshold": 0.00,
            "stop_loss_warn_pct": -0.05,
            "stop_loss_warn_reduce_ratio": 0.25,
            "stop_loss_pct": -0.08,
            "stop_loss_reduce_ratio": 0.50,
            "stop_loss_clear_pct": -0.10,
            "early_exit_pct": -0.06,
            "profit_protect_trigger_pct": 0.09,
            "profit_protect_reduce_ratio": 0.20,
            "take_profit_pct_1": 0.12,
            "take_profit_pct_2": 0.18,
            "take_profit_pct_3": 0.25,
            "take_profit_sell_ratio_1": 0.20,
            "take_profit_sell_ratio_2": 0.30,
            "take_profit_sell_ratio_3": 0.30,
            "trailing_stop_pct": -0.07,
            "account_drawdown_defense_pct": -0.15,
        },
        "version": "2.1",
        "status": "active",
    },
]

GOLD_KEYWORDS = ("黄金", "上海金", "金ETF", "金联接")
DIVIDEND_LOW_VOL_KEYWORDS = ("红利", "低波")


def get_strategy_template_seed_specs() -> list[dict]:
    """返回策略模板种子定义。"""
    return deepcopy(DEFAULT_STRATEGY_TEMPLATE_SPECS)


def build_default_strategy_templates() -> list[StrategyTemplate]:
    """构建默认策略模板模型对象。"""
    templates = []
    for spec in get_strategy_template_seed_specs():
        templates.append(
            StrategyTemplate(
                template_code=spec["template_code"],
                template_name=spec["template_name"],
                account_type=spec["account_type"],
                description=spec["description"],
                config_json=json.dumps(spec["config"], ensure_ascii=False),
                version=spec["version"],
                status=spec["status"],
            )
        )
    return templates


def upsert_default_strategy_templates(session) -> tuple[int, int]:
    """
    将默认策略模板同步到数据库。

    Returns:
        (created_count, updated_count)
    """
    created_count = 0
    updated_count = 0

    for spec in get_strategy_template_seed_specs():
        config_json = json.dumps(spec["config"], ensure_ascii=False)
        template = StrategyTemplate.query.filter_by(
            template_code=spec["template_code"]
        ).first()

        if template is None:
            session.add(
                StrategyTemplate(
                    template_code=spec["template_code"],
                    template_name=spec["template_name"],
                    account_type=spec["account_type"],
                    description=spec["description"],
                    config_json=config_json,
                    version=spec["version"],
                    status=spec["status"],
                )
            )
            created_count += 1
            continue

        template.template_name = spec["template_name"]
        template.account_type = spec["account_type"]
        template.description = spec["description"]
        template.config_json = config_json
        template.version = spec["version"]
        template.status = spec["status"]
        updated_count += 1

    session.commit()
    return created_count, updated_count


def is_gold_instrument_name(name: str) -> bool:
    """判断产品名称是否属于黄金类资产。"""
    normalized_name = (name or "").strip()
    return any(keyword in normalized_name for keyword in GOLD_KEYWORDS)


def is_dividend_low_vol_name(name: str) -> bool:
    """判断产品名称是否属于红利低波类资产。"""
    normalized_name = (name or "").strip()
    return any(keyword in normalized_name for keyword in DIVIDEND_LOW_VOL_KEYWORDS)


def infer_core_template_code(instrument_type: str, name: str) -> str:
    """为核心账户的产品推断模板编码。"""
    if is_gold_instrument_name(name):
        return "gold_hedge_template"
    if is_dividend_low_vol_name(name):
        return "dividend_low_vol_template"
    if instrument_type in ("etf", "lof"):
        return "core_index_template"
    return "core_active_fund_template"


def get_default_assignment_range(template_code: str, symbol: str = "", name: str = "") -> tuple[float, float]:
    """根据模板编码和产品信息返回默认目标仓位区间。"""
    normalized_name = (name or "").strip()
    normalized_symbol = (symbol or "").strip()

    if template_code == "core_index_template":
        if normalized_symbol == "513110" or "纳指" in normalized_name:
            return 0.20, 0.24
        if normalized_symbol == "161125" or "标普" in normalized_name:
            return 0.16, 0.20
        return 0.18, 0.22

    if template_code == "core_active_fund_template":
        return 0.10, 0.12

    if template_code == "gold_hedge_template":
        return 0.13, 0.15

    if template_code == "dividend_low_vol_template":
        return 0.13, 0.15

    if template_code == "tactical_theme_template":
        return 0.10, 0.30

    return 0.05, 0.20
