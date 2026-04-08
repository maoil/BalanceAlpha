"""
衡策投资系统 - 常量与枚举定义

集中管理所有状态值、类型值，避免硬编码
"""
from enum import Enum


# ============================================================
# 账户类型
# ============================================================
class AccountType(str, Enum):
    CORE = "core"           # 核心配置账户（长期）
    TACTICAL = "tactical"   # 战术轮动账户（短期）


# ============================================================
# 产品类型
# ============================================================
class InstrumentType(str, Enum):
    FUND = "fund"   # 场外基金
    ETF = "etf"     # ETF
    LOF = "lof"     # LOF
    CASH = "cash"   # 现金（虚拟资产）


# ============================================================
# 交易方式
# ============================================================
class TradeMode(str, Enum):
    EXCHANGE_TRADED = "exchange_traded"  # 场内交易
    EOD_NAV = "eod_nav"                  # 场外（按净值申赎）


# ============================================================
# 产品生命周期状态
# ============================================================
class InstrumentStatus(str, Enum):
    WATCHLIST = "watchlist"   # 观察中
    ACTIVE = "active"         # 启用中
    PAUSED = "paused"         # 暂停
    CLOSED = "closed"         # 已清仓
    ARCHIVED = "archived"     # 已归档


# ============================================================
# 持仓状态
# ============================================================
class PositionStatus(str, Enum):
    OPEN = "open"       # 持仓中
    CLOSED = "closed"   # 已清仓


# ============================================================
# 交易类型
# ============================================================
class TradeType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    SUBSCRIBE = "subscribe"           # 申购
    REDEEM = "redeem"                 # 赎回
    REBALANCE_BUY = "rebalance_buy"   # 再平衡买入
    REBALANCE_SELL = "rebalance_sell"  # 再平衡卖出
    DCA_BUY = "dca_buy"               # 定投买入
    STOP_LOSS_SELL = "stop_loss_sell"  # 止损卖出
    TAKE_PROFIT_SELL = "take_profit_sell"  # 止盈卖出
    MANUAL_ADJUST = "manual_adjust"   # 手工调整


# ============================================================
# 交易方向
# ============================================================
class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


# ============================================================
# 信号类型
# ============================================================
class SignalType(str, Enum):
    ALLOW_BUY = "allow_buy"       # 允许买入
    ALLOW_ADD = "allow_add"       # 允许加仓
    HOLD = "hold"                 # 持有
    REDUCE = "reduce"             # 减仓
    TAKE_PROFIT = "take_profit"   # 止盈
    STOP_LOSS = "stop_loss"       # 止损
    SUSPEND_ADD = "suspend_add"   # 暂停追加
    OBSERVE = "observe"           # 观察
    REBALANCE = "rebalance"       # 再平衡


# ============================================================
# 信号状态
# ============================================================
class SignalStatus(str, Enum):
    PENDING = "pending"           # 待处理
    ACKNOWLEDGED = "acknowledged"  # 已确认
    EXECUTED = "executed"          # 已执行
    EXPIRED = "expired"            # 已过期


# ============================================================
# 日志类型
# ============================================================
class LogType(str, Enum):
    SIGNAL = "signal"             # 策略信号
    PARAM_CHANGE = "param_change"  # 参数变更
    MANUAL = "manual"              # 手工操作
    ERROR = "error"                # 错误
    DATA_IMPORT = "data_import"    # 数据导入


# ============================================================
# 日志级别
# ============================================================
class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ============================================================
# 通用状态
# ============================================================
class Status(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


# ============================================================
# 回测状态
# ============================================================
class BacktestStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# 交易类型 → 方向映射
# ============================================================
TRADE_TYPE_SIDE_MAP = {
    TradeType.BUY: TradeSide.BUY,
    TradeType.SELL: TradeSide.SELL,
    TradeType.SUBSCRIBE: TradeSide.BUY,
    TradeType.REDEEM: TradeSide.SELL,
    TradeType.REBALANCE_BUY: TradeSide.BUY,
    TradeType.REBALANCE_SELL: TradeSide.SELL,
    TradeType.DCA_BUY: TradeSide.BUY,
    TradeType.STOP_LOSS_SELL: TradeSide.SELL,
    TradeType.TAKE_PROFIT_SELL: TradeSide.SELL,
    TradeType.MANUAL_ADJUST: TradeSide.BUY,  # 方向由具体情况决定
}


# ============================================================
# 信号类型中文映射（用于页面展示）
# ============================================================
SIGNAL_TYPE_LABELS = {
    SignalType.ALLOW_BUY: "允许买入",
    SignalType.ALLOW_ADD: "允许加仓",
    SignalType.HOLD: "持有",
    SignalType.REDUCE: "减仓",
    SignalType.TAKE_PROFIT: "止盈",
    SignalType.STOP_LOSS: "止损",
    SignalType.SUSPEND_ADD: "暂停追加",
    SignalType.OBSERVE: "观察",
    SignalType.REBALANCE: "再平衡",
}

# 信号类型 → Bootstrap 颜色样式
SIGNAL_TYPE_COLORS = {
    SignalType.ALLOW_BUY: "success",
    SignalType.ALLOW_ADD: "success",
    SignalType.HOLD: "primary",
    SignalType.REDUCE: "warning",
    SignalType.TAKE_PROFIT: "info",
    SignalType.STOP_LOSS: "danger",
    SignalType.SUSPEND_ADD: "secondary",
    SignalType.OBSERVE: "secondary",
    SignalType.REBALANCE: "warning",
}
