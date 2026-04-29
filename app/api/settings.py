import json

from flask import request

from app.api import bp
from app.api.responses import error, success
from app.extensions import db
from app.models.strategy_template import StrategyTemplate
from app.schemas.serializers import serialize_strategy_template
from app.services.log_service import LogService


@bp.get("/settings/strategy-templates")
def list_strategy_templates():
    templates = StrategyTemplate.query.order_by(
        StrategyTemplate.account_type.asc(),
        StrategyTemplate.template_code.asc(),
    ).all()
    return success([serialize_strategy_template(template) for template in templates])


@bp.get("/settings/strategy-templates/<int:template_id>")
def get_strategy_template(template_id: int):
    template = db.session.get(StrategyTemplate, template_id)
    if template is None:
        return error("not_found", "Strategy template not found", 404)
    return success(serialize_strategy_template(template))


@bp.patch("/settings/strategy-templates/<int:template_id>")
def update_strategy_template(template_id: int):
    template = db.session.get(StrategyTemplate, template_id)
    if template is None:
        return error("not_found", "Strategy template not found", 404)

    data = request.get_json(silent=True) or {}
    old_config = template.config_json

    if "config" in data:
        config_json = json.dumps(data["config"], ensure_ascii=False)
    elif "config_json" in data:
        config_json = data["config_json"]
        try:
            json.loads(config_json)
        except (TypeError, json.JSONDecodeError):
            return error("validation_error", "config_json must be valid JSON", 400)
    else:
        config_json = template.config_json

    template.template_name = data.get("template_name", template.template_name)
    template.description = data.get("description", template.description)
    template.config_json = config_json

    try:
        version = float(template.version or "1.0")
        template.version = f"{version + 0.1:.1f}"
    except ValueError:
        template.version = "1.1"

    db.session.commit()
    LogService.log(
        log_type="param_change",
        level="info",
        module="settings",
        message=f"Template {template.template_code} updated to v{template.version}",
        context={"old_config": old_config, "new_config": config_json},
    )

    return success(serialize_strategy_template(template))

