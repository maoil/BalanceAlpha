from flask import Blueprint, current_app, request

bp = Blueprint("api", __name__, url_prefix="/api/v1")


@bp.after_request
def add_cors_headers(response):
    allowed_origins = current_app.config.get("API_CORS_ORIGINS", [])
    origin = request.headers.get("Origin")

    if origin and ("*" in allowed_origins or origin in allowed_origins):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PATCH, PUT, DELETE, OPTIONS"
        )

    return response


@bp.get("/health")
def health():
    from app.api.responses import success

    return success(
        {
            "service": "balancealpha-api",
            "status": "ok",
            "version": "v1",
        }
    )


def register_api(app):
    from app.extensions import csrf

    from app.api import accounts, dashboard, instruments, positions, settings, signals, trades  # noqa: F401

    csrf.exempt(bp)
    app.register_blueprint(bp)

