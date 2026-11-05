"""Relay isolado de Meta CAPI para ViewContent do 7 Hábitos.

Sem credenciais no GitHub/HTML. Nenhum evento sem consentimento no cliente.
O endpoint é público; origem, token assinado e limitação de taxa reduzem abuso,
mas não autenticam a identidade de visitantes.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque

PIXEL_ID = "1780688656320725"
DEFAULT_ORIGIN = "https://7habitos.robertabitencourt.com.br"
LANDING_URL = DEFAULT_ORIGIN + "/"
ID_RE = re.compile(r"^rbvc-[a-f0-9]{32}$")
FBP_RE = re.compile(r"^fb\.1\.\d{10,16}\.\d{5,30}$")
VERSION_RE = re.compile(r"^v\d{1,2}\.\d$")
_TOKEN_TTL = 120
_MAX_BODY = 1200
_lock = threading.Lock()
_requests = defaultdict(deque)
_sent = {}


def _config():
    origin = os.environ.get("RB_CAPI_ALLOWED_ORIGIN", DEFAULT_ORIGIN).rstrip("/")
    if origin != DEFAULT_ORIGIN:
        raise ValueError("A origem permitida deve corresponder à landing do 7 Hábitos")
    token = os.environ.get("META_CAPI_ACCESS_TOKEN", "")
    signing = os.environ.get("RB_CAPI_SIGNING_SECRET", "")
    version = os.environ.get("META_GRAPH_VERSION", "")
    if not token or len(signing) < 32 or not VERSION_RE.fullmatch(version):
        raise ValueError("Configure token, segredo de 32+ caracteres e versão da Graph API")
    return token, signing, version, origin


def _response(start, code, data, origin=None):
    content = b"" if code.startswith("204") else json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(content))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("Vary", "Origin"),
    ]
    if origin == DEFAULT_ORIGIN:
        headers += [
            ("Access-Control-Allow-Origin", DEFAULT_ORIGIN),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ]
    start(code, headers)
    return [content]


def _signature(event_id, expiry, signing):
    msg = (event_id + "." + str(expiry)).encode("ascii")
    return hmac.new(signing.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _rate_limit(ip, now):
    # Janela por processo. Não substitui firewall/WAF no serviço publicado.
    with _lock:
        if len(_requests) > 2000:
            for key in list(_requests)[:500]:
                if not _requests[key] or _requests[key][-1] < now - 70:
                    del _requests[key]
        q = _requests[ip or "unknown"]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 24:
            return False
        q.append(now)
        return True


def _send_meta(event, access_token, version):
    url = "https://graph.facebook.com/" + version + "/" + PIXEL_ID + "/events"
    body = {"data": [event]}
    test_code = os.environ.get("META_CAPI_TEST_EVENT_CODE", "").strip()
    if test_code:
        body["test_event_code"] = test_code
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url, data=raw, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + access_token},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read(4096))
        return isinstance(result, dict) and result.get("events_received", 0) >= 1
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")
    origin = environ.get("HTTP_ORIGIN", "")
    if path == "/health":
        return _response(start_response, "200 OK", {"status": "ok"})

    if path not in ("/v1/view-token", "/v1/view-content"):
        return _response(start_response, "404 Not Found", {"ok": False})

    if origin != DEFAULT_ORIGIN:
        return _response(start_response, "403 Forbidden", {"ok": False})
    if method == "OPTIONS":
        return _response(start_response, "204 No Content", {}, origin)

    if not _rate_limit(environ.get("REMOTE_ADDR", ""), time.monotonic()):
        return _response(start_response, "429 Too Many Requests", {"ok": False}, origin)

    try:
        access_token, signing, version, _ = _config()
    except ValueError:
        return _response(start_response, "503 Service Unavailable", {"ok": False}, origin)

    if path == "/v1/view-token" and method == "GET":
        from urllib.parse import parse_qs
        params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=False)
        event_id = (params.get("event_id") or [""])[0]
        if not ID_RE.fullmatch(event_id):
            return _response(start_response, "400 Bad Request", {"ok": False}, origin)
        exp = int(time.time()) + _TOKEN_TTL
        return _response(start_response, "200 OK", {
            "event_id": event_id, "expires": exp,
            "signature": _signature(event_id, exp, signing)
        }, origin)

    if path != "/v1/view-content" or method != "POST":
        return _response(start_response, "405 Method Not Allowed", {"ok": False}, origin)

    if not environ.get("CONTENT_TYPE", "").lower().startswith("application/json"):
        return _response(start_response, "415 Unsupported Media Type", {"ok": False}, origin)
    try:
        length = int(environ.get("CONTENT_LENGTH", "-1"))
        if length <= 0 or length > _MAX_BODY:
            raise ValueError("invalid length")
        payload = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid json shape")
        event_id, expiry, signature = (
            payload.get("event_id"), payload.get("expires"), payload.get("signature")
        )
        if not isinstance(event_id, str) or not ID_RE.fullmatch(event_id):
            raise ValueError("invalid event id")
        if not isinstance(expiry, int) or isinstance(expiry, bool):
            raise ValueError("invalid expiry")
        now = int(time.time())
        if not now <= expiry <= now + _TOKEN_TTL:
            raise ValueError("expired")
        if not isinstance(signature, str) or not hmac.compare_digest(
            signature, _signature(event_id, expiry, signing)
        ):
            raise ValueError("invalid signature")
        if payload.get("consent") is not True:
            raise ValueError("no consent")
    except (ValueError, TypeError, UnicodeDecodeError, KeyError):
        return _response(start_response, "400 Bad Request", {"ok": False}, origin)

    fbp = payload.get("fbp")
    if fbp is not None and (not isinstance(fbp, str) or not FBP_RE.fullmatch(fbp)):
        return _response(start_response, "400 Bad Request", {"ok": False}, origin)

    # Somente parâmetros necessários; nenhum dado do formulário, compra,
    # saúde, nome, e-mail ou telefone é encaminhado à Meta.
    ua = str(environ.get("HTTP_USER_AGENT") or "")[:300]
    if not ua:
        return _response(start_response, "400 Bad Request", {"ok": False}, origin)
    user_data = {"client_user_agent": ua}
    if fbp:
        user_data["fbp"] = fbp
    # IP só será enviado com configuração explícita (LGPD).
    if os.environ.get("RB_CAPI_SEND_CLIENT_IP") == "1":
        try:
            ip = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
            if ip.is_global:
                user_data["client_ip_address"] = str(ip)
        except ValueError:
            pass

    with _lock:
        now_monotonic = time.monotonic()
        for key, when in list(_sent.items()):
            if when < now_monotonic - 600:
                _sent.pop(key, None)
        if event_id in _sent:
            return _response(start_response, "200 OK", {"ok": True, "duplicate": True}, origin)
        _sent[event_id] = now_monotonic

    event = {
        "event_name": "ViewContent",
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "website",
        "event_source_url": LANDING_URL,
        "user_data": user_data,
    }
    try:
        sent = _send_meta(event, access_token, version)
    except Exception:
        sent = False
    if not sent:
        with _lock:
            _sent.pop(event_id, None)
        return _response(start_response, "502 Bad Gateway", {"ok": False}, origin)
    return _response(start_response, "200 OK", {"ok": True}, origin)
