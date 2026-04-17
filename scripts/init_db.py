"""
数据库初始化脚本

功能：
1. 创建所有表
2. 插入种子数据（2个账户 + 5个策略模板 + 示例产品）

用法：
    python scripts/init_db.py
"""
import sys
from pathlib import Path

# 将项目根目录加入 Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import (
    Account, Instrument, StrategyAssignment,
)
from app.models.strategy_template import (
    build_default_strategy_templates,
    get_default_assignment_range,
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
        templates = build_default_strategy_templates()
        db.session.add_all(templates)
        db.session.commit()
        print(f"✓ 策略模板创建完成: {len(templates)}个模板")

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
                default_lower, default_upper = get_default_assignment_range(
                    template.template_code,
                    symbol=inst.symbol,
                    name=inst.name,
                )

                assignment = StrategyAssignment(
                    instrument_id=inst.id,
                    account_id=account.id,
                    template_id=template.id,
                    target_weight_lower=default_lower,
                    target_weight_upper=default_upper,
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
