import logging
import os
import secrets
from datetime import datetime, timezone

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from flask import Flask, jsonify, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

load_dotenv()

# ── 환경 판별 ──────────────────────────────────────────────────────────────
APP_ENV = os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV", "production")
IS_DEV = APP_ENV.lower() in ("development", "dev", "local")

# Google OAuth 로컬 개발용 HTTP 허용 (운영 환경에서는 절대 켜지 않음)
if IS_DEV:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# ── Flask 앱 설정 ──────────────────────────────────────────────────────────
app = Flask(__name__)

# 리버스 프록시(Cloud Run / Nginx) 뒤에서 올바른 IP · 프로토콜 처리
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# ── Firestore (refresh token 영구 저장) ────────────────────────────────────
from services.firestore_session import get_db as _get_fs_db  # noqa: E402

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]
_NO_RESTORE_PATHS = {"/login", "/auth/google", "/auth/callback", "/logout"}

# secret_key: 운영 환경에서 미설정 시 즉시 실패
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    if IS_DEV:
        _secret_key = "dev-secret-key-change-in-production"
    else:
        raise RuntimeError("FLASK_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
app.secret_key = _secret_key

# 세션 쿠키 보안 설정
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not IS_DEV,  # HTTPS 환경(Cloud Run)에서만 전송
)

# ── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.DEBUG if IS_DEV else logging.INFO)
logger = logging.getLogger(__name__)


# ── Firestore 세션 자동 복원 ──────────────────────────────────────────────
@app.before_request
def auto_restore_session():
    """device_id 쿠키로 Firestore에서 refresh_token을 찾아 세션을 자동 복원."""
    if "credentials" in session:
        return
    if request.path in _NO_RESTORE_PATHS or request.path.startswith("/static/"):
        return
    db = _get_fs_db()
    if db is None:
        return
    device_id = request.cookies.get("device_id")
    if not device_id:
        return
    try:
        doc = db.collection("sessions").document(device_id).get()
        if not doc.exists:
            return
        data = doc.to_dict()
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ.get("GOOGLE_CLIENT_ID"),
            client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
            scopes=_SCOPES,
        )
        creds.refresh(google.auth.transport.requests.Request())
        session.permanent = True
        session["credentials"] = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": _SCOPES,
        }
        session["user"] = data.get("user", {})
        session["sheet_id"] = data.get("sheet_id", "")
        session["sheet_title"] = data.get("sheet_title", "")
        session["worksheet_name"] = data.get("worksheet_name", "")
        db.collection("sessions").document(device_id).update({
            "refresh_token": creds.refresh_token,
            "updated_at": datetime.now(timezone.utc),
        })
    except Exception:
        logger.warning("Firestore session restore failed", exc_info=True)


# ── CSRF 보호 ─────────────────────────────────────────────────────────────
def get_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_globals():
    from version import VERSION
    return {"csrf_token": get_csrf_token, "app_version": VERSION}


@app.before_request
def validate_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    # 정적 파일·OAuth 콜백은 제외
    if request.path.startswith("/static/") or request.path in ("/auth/callback",):
        return
    expected = session.get("_csrf_token")
    provided = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
    )
    if not expected or not provided or not secrets.compare_digest(expected, provided):
        msg = "잘못된 요청입니다. 페이지를 새로고침 후 다시 시도해주세요."
        if request.is_json or request.content_type == "application/json":
            return jsonify({"ok": False, "error": msg}), 400
        return redirect(request.referrer or url_for("auth.login"))


# ── 전역 에러 핸들러 ───────────────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_unexpected_error(err):
    if isinstance(err, HTTPException):
        return err
    logger.exception("Unexpected error: %s", err)
    if request.is_json or request.content_type == "application/json":
        return jsonify({"ok": False, "error": "처리 중 오류가 발생했습니다."}), 500
    from flask import flash
    flash("처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", "error")
    if "credentials" not in session:
        return redirect(url_for("auth.login"))
    return redirect(url_for("main.index"))


# ── 블루프린트 등록 ────────────────────────────────────────────────────────
from routes.auth import auth_bp
from routes.sheet import sheet_bp
from routes.main import main_bp
from routes.item import item_bp
from routes.settings import settings_bp

app.register_blueprint(auth_bp)
app.register_blueprint(sheet_bp)
app.register_blueprint(main_bp)
app.register_blueprint(item_bp)
app.register_blueprint(settings_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=IS_DEV)
