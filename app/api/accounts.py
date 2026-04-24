from app.api import bp
from app.api.responses import success
from app.schemas.serializers import serialize_account
from app.services.account_service import AccountService


@bp.get("/accounts")
def list_accounts():
    return success([serialize_account(account) for account in AccountService.get_all()])

