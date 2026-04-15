"""
产品管理服务
"""
import json
from typing import Optional

from app.extensions import db
from app.models.instrument import Instrument
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate
from app.models.account import Account
from app.utils.constants import InstrumentStatus


class InstrumentService:
    """产品管理业务逻辑"""

    @staticmethod
    def get_all(status: Optional[str] = None, account_type: Optional[str] = None) -> list[Instrument]:
        """
        获取产品列表，支持状态和账户类型筛选

        Args:
            status: 产品状态筛选
            account_type: 账户类型筛选
        """
        query = Instrument.query
        if status:
            query = query.filter(Instrument.status == status)
        if account_type:
            query = query.filter(Instrument.default_account_type == account_type)
        return query.order_by(Instrument.symbol).all()

    @staticmethod
    def get_by_id(instrument_id: int) -> Optional[Instrument]:
        """按 ID 获取产品"""
        return db.session.get(Instrument, instrument_id)

    @staticmethod
    def get_by_symbol(symbol: str) -> Optional[Instrument]:
        """按代码获取产品"""
        return Instrument.query.filter_by(symbol=symbol).first()

    @staticmethod
    def create(data: dict) -> Instrument:
        """
        新增产品

        Args:
            data: 产品数据字典，包含 symbol, name, instrument_type 等
        Returns:
            新创建的产品对象
        """
        instrument = Instrument(
            symbol=data["symbol"].strip(),
            name=data["name"].strip(),
            instrument_type=data["instrument_type"],
            market=data.get("market", ""),
            trade_mode=data.get("trade_mode", "eod_nav"),
            default_account_type=data.get("default_account_type", "core"),
            default_strategy_template=data.get("default_strategy_template", ""),
            is_dca_eligible=data.get("is_dca_eligible", False),
            status=data.get("status", InstrumentStatus.ACTIVE.value),
            notes=data.get("notes", ""),
        )
        db.session.add(instrument)
        db.session.commit()

        # 自动创建策略绑定
        InstrumentService._auto_create_assignment(instrument, data)

        return instrument

    @staticmethod
    def _auto_create_assignment(instrument: Instrument, data: dict) -> None:
        """新增产品时自动创建策略绑定（如果未选模板则自动推断）"""
        template_code = data.get("default_strategy_template", "")
        account_type = data.get("default_account_type", "core")

        # 如果没有选模板，根据产品类型和账户类型自动推断
        if not template_code:
            template_code = InstrumentService._infer_template_code(
                data.get("instrument_type", "fund"),
                account_type,
                data.get("name", ""),
            )
            # 同步更新产品的 default_strategy_template 字段
            if template_code:
                instrument.default_strategy_template = template_code

        template = StrategyTemplate.query.filter_by(template_code=template_code).first()
        account = Account.query.filter_by(account_type=account_type).first()

        if template and account:
            # 检查是否已有绑定
            existing = StrategyAssignment.query.filter_by(
                instrument_id=instrument.id,
                account_id=account.id,
            ).first()
            if existing:
                return

            # 读取模板默认权重配置
            import json
            config = json.loads(template.config_json) if template.config_json else {}
            default_lower = config.get("target_weight_lower", 0.0)
            default_upper = config.get("target_weight_upper", 0.0)

            assignment = StrategyAssignment(
                instrument_id=instrument.id,
                account_id=account.id,
                template_id=template.id,
                target_weight_lower=data.get("target_weight_lower", default_lower),
                target_weight_upper=data.get("target_weight_upper", default_upper),
                allow_dca=data.get("is_dca_eligible", False),
                allow_rebalance=True,
            )
            db.session.add(assignment)
            db.session.commit()

    @staticmethod
    def _infer_template_code(instrument_type: str, account_type: str, name: str) -> str:
        """根据产品类型和账户类型自动推断最合适的策略模板"""
        if account_type == "tactical":
            return "tactical_theme_template"
        # 核心账户
        if instrument_type in ("etf", "lof"):
            if "黄金" in name or "金" in name:
                return "gold_hedge_template"
            return "core_index_template"
        if instrument_type == "fund":
            if "黄金" in name or "金" in name:
                return "gold_hedge_template"
            return "core_active_fund_template"
        return "core_index_template"

    @staticmethod
    def update(instrument_id: int, data: dict) -> Optional[Instrument]:
        """更新产品信息"""
        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return None

        for field in ["name", "instrument_type", "market", "trade_mode",
                       "default_account_type", "default_strategy_template",
                       "is_dca_eligible", "status", "notes"]:
            if field in data:
                setattr(instrument, field, data[field])

        db.session.commit()

        # 确保策略绑定存在（补救之前没创建的情况）
        InstrumentService._auto_create_assignment(instrument, data)

        return instrument

    @staticmethod
    def update_status(instrument_id: int, new_status: str) -> Optional[Instrument]:
        """
        更新产品状态（软操作，不做物理删除）

        PRD 规则：已有历史交易记录的产品不得直接物理删除
        """
        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return None

        instrument.status = new_status
        db.session.commit()
        return instrument

    @staticmethod
    def get_active_instruments() -> list[Instrument]:
        """获取所有启用中的产品"""
        return Instrument.query.filter(
            Instrument.status.in_([InstrumentStatus.ACTIVE.value, InstrumentStatus.WATCHLIST.value])
        ).all()
