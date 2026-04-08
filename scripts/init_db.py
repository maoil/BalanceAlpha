"""
数据库初始化脚本

功能：
1. 创建所有表
2. 插入种子数据（2个账户 + 4个策略模板 + 示例产品）

用法：
    python scripts/init_db.py
"""
import sys
import json
from pathlib import Path

# 将项目根目录加入 Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import (
    Account, Instrument, StrategyTemplate, StrategyAssignment,
)


def init_database():
    """初始化数据库并插入种子数据"""
    app = create_app()

    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✓ 数据库表创建完成")

        # 检查是否已有数据
        if Account.query.count() > 0:
            print("⚠ 数据库已有数据，跳过种子数据插入。如需重新初始化，请删除 data/balancealpha.db 后重试。")
            return

        # ==============================
        # 1. 创建账户
        # ==============================
        core_account = Account(
            account_code="core",
            account_name="核心配置账户",
            account_type="core",
            description="长期投资、定投、资产配置、月度再平衡",
            status="active",
        )
        tactical_account = Account(
            account_code="tactical",
            account_name="战术轮动账户",
            account_type="tactical",
            description="主题轮动、趋势交易、主动风控",
            status="active",
        )
        db.session.add_all([core_account, tactical_account])
        db.session.commit()
        print("✓ 账户创建完成: 核心配置账户, 战术轮动账户")

        # ==============================
        # 2. 创建策略模板 (PRD §7.6 / §20)
        # ==============================
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
                    "drawdown_tier_1": -0.05,
                    "drawdown_tier_2": -0.10,
                    "drawdown_tier_3": -0.20,
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
                    "score_threshold_buy": 70,
                    "score_threshold_hold": 55,
                    "dca_allowed": True,
                    "dca_frequency": "monthly",
                    "manager_change_alert": True,
                    "style_drift_alert": True,
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
                    "hedge_only": True,
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
                    "take_profit_sell_ratio_1": 0.33,
                    "take_profit_sell_ratio_2": 0.33,
                    "trailing_stop_pct": -0.08,
                    "account_drawdown_defense_pct": -0.15,
                }, ensure_ascii=False),
                version="1.0",
                status="active",
            ),
        ]
        db.session.add_all(templates)
        db.session.commit()
        print("✓ 策略模板创建完成: 4个模板")

        # ==============================
        # 3. 创建示例产品
        # ==============================
        sample_instruments = [
            Instrument(
                symbol="513500",
                name="标普500ETF",
                instrument_type="etf",
                market="cn_exchange",
                trade_mode="exchange_traded",
                default_account_type="core",
                default_strategy_template="core_index_template",
                is_dca_eligible=True,
                status="active",
                notes="跟踪标普500指数",
            ),
            Instrument(
                symbol="159941",
                name="纳指ETF",
                instrument_type="etf",
                market="cn_exchange",
                trade_mode="exchange_traded",
                default_account_type="core",
                default_strategy_template="core_index_template",
                is_dca_eligible=True,
                status="active",
                notes="跟踪纳斯达克100指数",
            ),
            Instrument(
                symbol="518880",
                name="黄金ETF",
                instrument_type="etf",
                market="cn_exchange",
                trade_mode="exchange_traded",
                default_account_type="core",
                default_strategy_template="gold_hedge_template",
                is_dca_eligible=False,
                status="active",
                notes="跟踪Au99.99现货黄金",
            ),
        ]
        db.session.add_all(sample_instruments)
        db.session.commit()
        print("✓ 示例产品创建完成: 513500, 159941, 518880")

        # ==============================
        # 4. 创建策略绑定
        # ==============================
        for inst in sample_instruments:
            template = StrategyTemplate.query.filter_by(
                template_code=inst.default_strategy_template
            ).first()
            account = Account.query.filter_by(
                account_type=inst.default_account_type
            ).first()

            if template and account:
                assignment = StrategyAssignment(
                    instrument_id=inst.id,
                    account_id=account.id,
                    template_id=template.id,
                    target_weight_lower=json.loads(template.config_json).get("target_weight_lower", 0.1),
                    target_weight_upper=json.loads(template.config_json).get("target_weight_upper", 0.3),
                    allow_dca=inst.is_dca_eligible,
                    allow_rebalance=True,
                    status="active",
                )
                db.session.add(assignment)

        db.session.commit()
        print("✓ 策略绑定创建完成")

        print("\n========================================")
        print("✅ 数据库初始化完成！")
        print(f"   数据库文件: data/balancealpha.db")
        print(f"   账户数: {Account.query.count()}")
        print(f"   策略模板数: {StrategyTemplate.query.count()}")
        print(f"   产品数: {Instrument.query.count()}")
        print(f"   策略绑定数: {StrategyAssignment.query.count()}")
        print("========================================")
        print("\n现在可以运行: python run.py")


if __name__ == "__main__":
    init_database()
