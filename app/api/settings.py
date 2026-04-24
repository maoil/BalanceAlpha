from app.api import bp
from app.api.responses import success
from app.models.strategy_template import StrategyTemplate
from app.schemas.serializers import serialize_strategy_template


@bp.get("/settings/strategy-templates")
def list_strategy_templates():
    templates = StrategyTemplate.query.order_by(
        StrategyTemplate.account_type.asc(),
        StrategyTemplate.template_code.asc(),
    ).all()
    return success([serialize_strategy_template(template) for template in templates])

