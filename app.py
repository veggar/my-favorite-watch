import logging
import os
import secrets
from datetime import timedelta
from urllib.parse import urlunsplit

import google.auth.transport.requests
from flask import Flask, g, jsonify, redirect, request, session, url_for
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

# ── Firestore (사용자 설정 · 기기 세션) ────────────────────────────────────
from services.firestore_session import (  # noqa: E402
    apply_sheet_to_session as _apply_sheet_to_session,
    get_db as _get_fs_db,
    get_user_config as _get_user_config,
    restore_device_context as _restore_device_context,
    touch_device_session as _touch_device_session,
    update_refresh_token as _update_refresh_token,
    upgrade_legacy_device as _upgrade_legacy_device,
)
from services.google_credentials import (  # noqa: E402
    build_credentials as _build_credentials,
    session_payload as _session_payload,
)
from services.user_identity import USER_KEY_VERSION as _USER_KEY_VERSION  # noqa: E402

_NO_RESTORE_PATHS = {"/login", "/auth/google", "/auth/callback", "/logout", "/logout-all"}

# secret_key: 운영 환경에서 미설정 시 즉시 실패
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    if IS_DEV:
        _secret_key = "dev-secret-key-change-in-production"
    else:
        raise RuntimeError("FLASK_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
app.secret_key = _secret_key

# 세션 수명
#
# Flask 기본값은 31일이다. 그러나 장기 로그인 유지는 Flask 세션이 아니라
# `device_id` 쿠키(90일) + Firestore refresh_token 이 담당한다. 세션이 만료돼도
# auto_restore_session 이 같은 요청에서 세션을 재구성하므로 사용자가 체감하는
# 로그인 유지 기간(동일 디바이스 기준 90일)에는 영향이 없다.
# 따라서 세션 쿠키 자체는 짧게 유지해 탈취 시 노출 창을 줄인다.
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "12"))

# 세션 쿠키 보안 설정
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not IS_DEV,  # HTTPS 환경(Cloud Run)에서만 전송
    PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_LIFETIME_HOURS),
    # 요청마다 만료 시각을 연장한다(사용 중에는 끊기지 않도록).
    SESSION_REFRESH_EACH_REQUEST=True,
)

# ── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.DEBUG if IS_DEV else logging.INFO)
logger = logging.getLogger(__name__)


# ── 공식 host 고정 (P0-1) ─────────────────────────────────────────────────
@app.before_request
def enforce_canonical_host():
    """운영에서 공식 도메인이 아닌 host 로 들어오면 canonical URL 로 308 이동.

    콜백은 `REDIRECT_URI` 의 host 로만 돌아오므로, 다른 host(예: Cloud Run
    기본 URL)에서 로그인을 시작하면 state 를 담은 세션 쿠키가 콜백 요청에
    실리지 않아 `/login` 루프가 된다. 308 은 메서드와 본문을 보존한다.
    """
    if IS_DEV:
        return
    from routes.auth import canonical_host

    expected = canonical_host()
    if not expected or request.host == expected:
        return
    target = urlunsplit(
        ("https", expected, request.path, request.query_string.decode("utf-8", "ignore"), "")
    )
    logger.info("canonical host redirect applied (path=%s)", request.path)
    return redirect(target, code=308)


# ── Firestore 세션 자동 복원 ──────────────────────────────────────────────
@app.before_request
def auto_restore_session():
    """device_id 쿠키로 기기 세션을 찾아 Flask 세션을 자동 복원한다.

    조회 순서는 `device_sessions/{device_id}` → `users/{user_key}` 이다.
    전환 기간 동안에는 레거시 `sessions` 문서도 읽고, 복원에 성공하면
    신규 구조로 옮긴 뒤 원문 개인정보를 제거한다(P0-3 · P0-4).
    """
    if session.get("credentials") and session.get("user_key"):
        return
    if request.path in _NO_RESTORE_PATHS or request.path.startswith("/static/"):
        return
    if _get_fs_db() is None:
        return
    device_id = request.cookies.get("device_id")
    if not device_id:
        return

    ctx = _restore_device_context(device_id)
    if not ctx:
        return
    user_key = ctx.get("user_key") or ""
    if not user_key:
        # 레거시 문서에 user_key 가 없다. 이메일로 사용자를 추정하지 않고
        # 재로그인을 요구한다(계정 혼입 방지).
        logger.info("device session without user_key; re-login required")
        return

    try:
        creds = _build_credentials(token=None, refresh_token=ctx["refresh_token"])
        creds.refresh(google.auth.transport.requests.Request())
    except Exception as e:
        # 예외 원문에는 토큰 · 문서 경로가 포함될 수 있어 타입만 남긴다.
        # (테스트 상태 앱의 7일 만료도 이 경로로 관측된다 → 재로그인 필요)
        logger.warning("Session restore failed at token refresh (%s)", type(e).__name__)
        return

    # 이전 계정의 잔여 값이 섞이지 않도록 사용자 관련 키만 비우고 다시 채운다.
    # (_csrf_token 은 유지해야 진행 중인 POST 요청이 깨지지 않는다)
    for key in ("user", "sheet_id", "sheet_title", "worksheet_name"):
        session.pop(key, None)
    session.permanent = True
    # 세션에는 access token 과 만료 시각만 저장한다 (client_secret /
    # refresh_token 은 서명만 된 쿠키에 담기지 않는다).
    session["credentials"] = _session_payload(creds)
    session["user_key"] = user_key
    session["user_key_version"] = _USER_KEY_VERSION
    # 표시용 이름 · 프로필은 저장하지 않으므로 자동 복원 시에는 비어 있다.
    session["user"] = {}
    _apply_sheet_to_session(_get_user_config(user_key))

    if ctx["source"] == "legacy":
        _upgrade_legacy_device(device_id, user_key, creds.refresh_token or ctx["refresh_token"])
    else:
        if creds.refresh_token and creds.refresh_token != ctx["refresh_token"]:
            _update_refresh_token(device_id, creds.refresh_token)
        else:
            _touch_device_session(device_id)

    # 세션 복원에 성공했으므로 device_id 쿠키 만료를 연장한다.
    # (연장하지 않으면 계속 사용 중인 사용자도 최초 로그인 90일 후 로그아웃된다)
    g.renew_device_id = device_id


@app.after_request
def renew_device_cookie(resp):
    """auto_restore_session 이 성공한 요청에서 device_id 쿠키를 갱신한다."""
    device_id = getattr(g, "renew_device_id", None)
    if device_id:
        from routes.auth import set_device_cookie
        set_device_cookie(resp, device_id)
    return resp


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
