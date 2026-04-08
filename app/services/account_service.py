"""
账户管理服务
"""
from typing import Optional

from app.extensions import db
from app.models.account import Account
from app.models.position import Position


class AccountService:
    """账户管理业务逻辑"""

    @staticmethod
    def get_all() -> list[Account]:
        """获取所有账户"""
        return Account.query.order_by(Account.id).all()

    @staticmethod
    def get_by_id(account_id: int) -> Optional[Account]:
        """按 ID 获取账户"""
        return db.session.get(Account, account_id)

    @staticmethod
    def get_by_code(account_code: str) -> Optional[Account]:
        """按编码获取账户"""
        return Account.query.filter_by(account_code=account_code).first()

    @staticmethod
    def get_account_summary(account_id: int) -> dict:
        """
        计算账户汇总信息

        Returns:
            包含总市值、总盈亏、持仓数量等的字典
        """
        positions = Position.query.filter_by(
            account_id=account_id,
            position_status="open"
        ).all()

        total_market_value = sum(p.market_value or 0 for p in positions)
        total_cost = sum((p.quantity or 0) * (p.avg_cost or 0) for p in positions)
        total_unrealized_pnl = sum(p.unrealized_pnl or 0 for p in positions)
        position_count = len(positions)

        return {
            "total_market_value": total_market_value,
            "total_cost": total_cost,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_unrealized_pnl_pct": (
                total_unrealized_pnl / total_cost if total_cost > 0 else 0
            ),
            "position_count": position_count,
        }

    @staticmethod
    def get_all_summaries() -> dict:
        """获取所有账户的汇总信息"""
        accounts = AccountService.get_all()
        summaries = {}
        for account in accounts:
            summaries[account.account_code] = {
                "account": account,
                "summary": AccountService.get_account_summary(account.id),
            }
        return summaries
