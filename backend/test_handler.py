"""Minimal WSGI handler to verify FC runtime mechanism."""
import json

def handler(environ, start_response):
    status = "200 OK"
    headers = [("Content-Type", "application/json")]
    start_response(status, headers)
    body = json.dumps({"status": "ok", "method": environ.get("REQUEST_METHOD"),
                       "path": environ.get("PATH_INFO")})
    return [body.encode()]
