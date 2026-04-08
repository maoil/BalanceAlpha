"""
参数配置路由
"""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.extensions import db
from app.models.strategy_template import StrategyTemplate
from app.services.log_service import LogService

bp = Blueprint("settings", __name__)


@bp.route("/")
def list_templates():
    """策略模板列表"""
    templates = StrategyTemplate.query.order_by(StrategyTemplate.account_type).all()
    return render_template("settings/list.html", templates=templates)


@bp.route("/templates/<int:template_id>", methods=["GET", "POST"])
def edit_template(template_id: int):
    """编辑策略模板参数"""
    template = db.session.get(StrategyTemplate, template_id)
    if not template:
        flash("模板不存在", "error")
        return redirect(url_for("settings.list_templates"))

    if request.method == "POST":
        old_config = template.config_json
        new_config = request.form.get("config_json", "{}")

        # 验证 JSON 格式
        try:
            json.loads(new_config)
        except json.JSONDecodeError:
            flash("参数 JSON 格式错误", "error")
            return redirect(url_for("settings.edit_template", template_id=template_id))

        template.template_name = request.form.get("template_name", template.template_name)
        template.description = request.form.get("description", template.description)
        template.config_json = new_config

        # 版本号递增
        try:
            ver = float(template.version or "1.0")
            template.version = f"{ver + 0.1:.1f}"
        except ValueError:
            template.version = "1.1"

        db.session.commit()

        # 记录参数变更日志
        LogService.log(
            log_type="param_change",
            level="info",
            module="settings",
            message=f"模板 {template.template_code} 参数已更新至 v{template.version}",
            context={"old_config": old_config, "new_config": new_config},
        )

        flash(f"模板参数已更新至 v{template.version}", "success")
        return redirect(url_for("settings.list_templates"))

    # 格式化 JSON 便于编辑
    try:
        formatted_config = json.dumps(json.loads(template.config_json), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        formatted_config = template.config_json or "{}"

    return render_template(
        "settings/edit.html",
        template=template,
        formatted_config=formatted_config,
    )
