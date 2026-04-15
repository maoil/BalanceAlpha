"""
修复策略绑定：为所有缺少 strategy_assignment 的活跃产品自动创建绑定。

产品 → 策略模板映射规则：
  core + etf/lof       → core_index_template
  core + fund(黄金相关) → gold_hedge_template
  core + fund(其他)    → core_active_fund_template
  tactical + *         → tactical_theme_template

同时修复 instruments.default_strategy_template 字段。
"""
import sqlite3
import sys
from datetime import datetime

DB_PATH = r"c:\Users\guangxin.yang\PycharmProjects\BalanceAlpha\data\balancealpha.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. 获取所有策略模板
    templates = {}
    for row in c.execute("SELECT id, template_code, account_type FROM strategy_templates WHERE status='active'"):
        templates[row["template_code"]] = {"id": row["id"], "account_type": row["account_type"]}
    print(f"策略模板: {list(templates.keys())}")

    # 2. 获取所有账户
    accounts = {}
    for row in c.execute("SELECT id, account_type FROM accounts WHERE status='active'"):
        accounts[row["account_type"]] = row["id"]
    print(f"账户: {accounts}")

    # 3. 获取所有活跃产品
    instruments = c.execute(
        "SELECT id, symbol, name, instrument_type, default_account_type, default_strategy_template "
        "FROM instruments WHERE status='active'"
    ).fetchall()
    print(f"\n活跃产品: {len(instruments)} 个")

    # 4. 检查已有绑定
    existing = set()
    for row in c.execute("SELECT instrument_id, account_id FROM strategy_assignments"):
        existing.add((row["instrument_id"], row["account_id"]))
    print(f"已有绑定: {len(existing)} 条")

    # 5. 为缺失绑定的产品创建
    created = 0
    for inst in instruments:
        account_type = inst["default_account_type"] or "core"
        account_id = accounts.get(account_type)
        if not account_id:
            print(f"  [WARN] {inst['symbol']}: cannot find account '{account_type}'")
            continue

        if (inst["id"], account_id) in existing:
            print(f"  [SKIP] {inst['symbol']}: already has assignment")
            continue

        # 自动选择策略模板
        template_code = _match_template(
            inst["instrument_type"],
            account_type,
            inst["name"],
        )
        template_info = templates.get(template_code)
        if not template_info:
            print(f"  [WARN] {inst['symbol']}: cannot find template '{template_code}'")
            continue

        # 设置默认权重区间
        weight_lower, weight_upper = _default_weights(template_code, len(instruments))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """INSERT INTO strategy_assignments 
               (instrument_id, account_id, template_id, 
                target_weight_lower, target_weight_upper,
                allow_dca, allow_rebalance, custom_config_json, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, '{}', 'active', ?, ?)""",
            (
                inst["id"], account_id, template_info["id"],
                weight_lower, weight_upper,
                1 if account_type == "core" else 0,  # 核心账户允许定投
                1,  # 允许再平衡
                now, now,
            )
        )

        # 同步更新 instrument 的 default_strategy_template
        c.execute(
            "UPDATE instruments SET default_strategy_template = ? WHERE id = ?",
            (template_code, inst["id"]),
        )

        print(f"  [OK] {inst['symbol']}: "
              f"→ 账户={account_type}, 模板={template_code}, "
              f"权重=[{weight_lower:.0%}, {weight_upper:.0%}]")
        created += 1

    conn.commit()
    conn.close()

    print(f"\n{'=' * 50}")
    print(f"完成！新建 {created} 条策略绑定。")
    if created > 0:
        print("现在可以重新生成信号了。")


def _match_template(instrument_type: str, account_type: str, name: str) -> str:
    """根据产品类型和账户类型自动匹配策略模板"""
    if account_type == "tactical":
        return "tactical_theme_template"

    # 核心账户
    if instrument_type in ("etf", "lof"):
        # 检查是否是黄金 ETF
        if "黄金" in name or "金" in name:
            return "gold_hedge_template"
        return "core_index_template"
    
    if instrument_type == "fund":
        if "黄金" in name or "金" in name:
            return "gold_hedge_template"
        return "core_active_fund_template"

    return "core_index_template"


def _default_weights(template_code: str, total_count: int) -> tuple:
    """根据模板类型返回默认权重区间"""
    weight_map = {
        "core_index_template": (0.15, 0.30),
        "core_active_fund_template": (0.10, 0.25),
        "gold_hedge_template": (0.05, 0.15),
        "tactical_theme_template": (0.10, 0.30),
    }
    return weight_map.get(template_code, (0.05, 0.20))


if __name__ == "__main__":
    main()
