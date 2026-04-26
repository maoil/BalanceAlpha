from flask import jsonify


def success(data=None, status: int = 200, meta: dict | None = None):
    payload = {"data": data}
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def error(code: str, message: str, status: int = 400):
    return jsonify({"error": {"code": code, "message": message}}), status

