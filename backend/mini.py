"""FC Python runtime adapter - installs deps at cold start if needed."""
import base64
import json
import os
import subprocess
import sys
import traceback
from io import BytesIO

_INSTALLED = False
_flask_app = None


def _install_deps():
    """Install required packages at FC cold start."""
    global _INSTALLED
    if _INSTALLED:
        return
    result = subprocess.run([
        sys.executable, "-m", "pip", "install",
        "flask", "pymupdf", "httpx",
        "-i", "https://mirrors.aliyun.com/pypi/simple/",
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or result.stdout[-2000:])
    _INSTALLED = True


def _get_flask_app():
    global _flask_app
    if _flask_app is not None:
        return _flask_app, None
    try:
        from app import app as flask_app
        _flask_app = flask_app
        return _flask_app, None
    except Exception as e:
        return None, str(e)


def _build_environ(event: dict) -> dict:
    body = event.get("body", "") or ""
    is_b64 = event.get("isBase64Encoded", False)
    if is_b64 and body:
        body = base64.b64decode(body)
    else:
        body = body.encode("utf-8") if isinstance(body, str) else body

    headers = event.get("headers", {}) or {}
    qs_params = event.get("queryParameters", {}) or {}
    query_string = "&".join(f"{k}={v}" for k, v in qs_params.items())
    path = event.get("rawPath", "/")
    # FC Python runtime puts method in different locations depending on version
    rc = event.get("requestContext") or {}
    method = event.get("httpMethod") or rc.get("httpMethod") or rc.get("http", {}).get("method") or "GET"

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SERVER_NAME": "fcapp.run",
        "SERVER_PORT": "443",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.input": BytesIO(body),
        "wsgi.errors": BytesIO(),
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": None,
    }
    for key, value in headers.items():
        if key.lower() == "content-type":
            environ["CONTENT_TYPE"] = value
        elif key.lower() == "content-length":
            environ["CONTENT_LENGTH"] = value
        wsgi_key = "HTTP_" + key.upper().replace("-", "_")
        environ[wsgi_key] = value
    return environ


def app(event, context):
    """FC HTTP trigger handler."""
    flask_app, err = _get_flask_app()
    if flask_app is None:
        try:
            _install_deps()
            flask_app, err = _get_flask_app()
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "pip install failed", "detail": str(e)}),
            }

    if flask_app is None:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "import failed", "detail": err}),
        }

    try:
        if isinstance(event, bytes):
            event = json.loads(event.decode("utf-8"))
        environ = _build_environ(event)
        response_status = []
        response_headers = []

        def start_response(status, headers, exc_info=None):
            response_status.append(status)
            response_headers.extend(headers)

        body_chunks = []
        for chunk in flask_app(environ, start_response):
            body_chunks.append(chunk)

        body_bytes = b"".join(body_chunks)
        try:
            body_str = body_bytes.decode("utf-8")
            is_b64 = False
        except UnicodeDecodeError:
            body_str = base64.b64encode(body_bytes).decode("utf-8")
            is_b64 = True

        status_code = int(response_status[0].split()[0]) if response_status else 200
        resp_headers = {}
        for key, value in response_headers:
            resp_headers[key] = value

        return {
            "statusCode": status_code,
            "headers": resp_headers,
            "body": body_str,
            "isBase64Encoded": is_b64,
        }
    except Exception:
        tb = traceback.format_exc()
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "handler error", "traceback": tb[:2000]}),
        }
