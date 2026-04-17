from app.models.strategy_template import (
    build_default_strategy_templates,
    get_default_assignment_range,
    infer_core_template_code,
)


def test_template_seed_helpers_cover_core_gold_and_dividend_ranges(app):
    templates = build_default_strategy_templates()
    template_codes = {template.template_code for template in templates}

    assert "core_index_template" in template_codes
    assert "tactical_theme_template" in template_codes
    assert any(template.version == "2.1" for template in templates if template.template_code == "tactical_theme_template")

    assert infer_core_template_code("etf", "纳指100ETF") == "core_index_template"
    assert infer_core_template_code("fund", "天弘上海金ETF联接C") == "gold_hedge_template"
    assert infer_core_template_code("fund", "南方标普中国A股大盘红利低波50联接C") == "dividend_low_vol_template"

    assert get_default_assignment_range("core_index_template", "513110", "纳指100ETF") == (0.20, 0.24)
    assert get_default_assignment_range("gold_hedge_template", "014662", "天弘上海金ETF联接C") == (0.13, 0.15)
