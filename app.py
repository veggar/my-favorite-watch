import logging
import os
import secrets
from datetime import timedelta
from urllib.parse import urlunsplit

import google.auth.transport.requests
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
    OAUTH_SCOPE_VERSION as _OAUTH_SCOPE_VERSION,
    build_credentials as _build_credentials,
    session_payload as _session_payload,
)
from services.hybrid_session import HybridSessionInterface  # noqa: E402
from services.session_state import auth_timestamp, is_auth_fresh  # noqa: E402
from services.user_identity import USER_KEY_VERSION as _USER_KEY_VERSION  # noqa: E402

_NO_RESTORE_PATHS = {
    "/login", "/auth/google", "/auth/callback", "/logout", "/logout-all",
    "/privacy", "/terms", "/manifest.webmanifest", "/favicon.ico",
}

# secret_key: 운영 환경에서 미설정 시 즉시 실패
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    if IS_DEV:
        _secret_key = "dev-secret-key-change-in-production"
    else:
        raise RuntimeError("FLASK_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
app.secret_key = _secret_key

# ── 서버 측 세션 (task-2026-08-003) ────────────────────────────────────────
# 민감한 세션 값(credentials · user_key · user · 시트 캐시)은 Firestore
# `server_sessions` 에 두고, 쿠키에는 예측 불가능한 session_id 만 남긴다.
# Firestore 미구성(로컬 개발) 시 표준 쿠키 세션으로 자동 폴백한다.
app.session_interface = HybridSessionInterface()

# ── 세션 쿠키 (Firebase Hosting 제약) ──────────────────────────────────────
#
# 커스텀 도메인은 Firebase Hosting 을 경유해 Cloud Run 으로 전달된다.
# Firebase Hosting 은 백엔드로 요청을 넘길 때 **`__session` 이라는 이름의
# 쿠키 하나만 통과시키고 나머지 쿠키는 모두 제거**한다. 따라서
#
#   - 쿠키 이름은 반드시 `__session` 이어야 하고,
#   - 예전처럼 `session` + `device_id` 두 개로 나눌 수 없다.
#
# 대신 수명 2계층을 코드로 강제한다(조치안 개정 2판 2.2).
#
#   장기(90일)  device_id · user_key · 시트 캐시  → 쿠키 수명이 담당
#   단기(12시간) credentials(access token) · 표시 정보
#               → `auth_at` 을 검사해 만료 시 세션에서 제거하고,
#                 Firestore refresh_token 으로 즉시 재구성한다.
SESSION_COOKIE_NAME = "__session"

# 쿠키(=기기 식별) 수명. 마지막 요청 기준으로 슬라이딩 갱신된다.
DEVICE_SESSION_DAYS = 90

# access token 계층의 신선도. 초과하면 credentials 를 폐기한다.
# (기존 SESSION_LIFETIME_HOURS 환경 변수를 그대로 재사용한다)
AUTH_FRESHNESS_HOURS = int(
    os.environ.get("AUTH_FRESHNESS_HOURS")
    or os.environ.get("SESSION_LIFETIME_HOURS", "12")
)

app.config.update(
    SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=not IS_DEV,  # HTTPS 환경(Cloud Run)에서만 전송
    PERMANENT_SESSION_LIFETIME=timedelta(days=DEVICE_SESSION_DAYS),
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


# ── 단기 계층 만료 (P0-5) ─────────────────────────────────────────────────
@app.before_request
def expire_stale_credentials():
    """`auth_at` 이 오래된 세션에서 access token 계층만 폐기한다.

    쿠키는 하나뿐이고 수명이 90일이므로, 짧은 계층은 코드로 만든다.
    `device_id` · `user_key` · 시트 캐시는 남기므로 이어지는
    `auto_restore_session` 이 Firestore refresh_token 으로 즉시 재구성한다.
    사용자에게는 재로그인이 발생하지 않는다.
    """
    if request.path.startswith("/static/"):
        return
    if not session.get("credentials"):
        return
    if is_auth_fresh(session.get("auth_at")):
        return
    session.pop("credentials", None)
    session.pop("user", None)
    logger.info("auth freshness expired; access token layer dropped")


# ── Firestore 세션 자동 복원 ──────────────────────────────────────────────
@app.before_request
def auto_restore_session():
    """세션의 device_id 로 기기 세션을 찾아 Flask 세션을 자동 복원한다.

    조회 순서는 `device_sessions/{device_id}` → `users/{user_key}` 이다.
    전환 기간 동안에는 레거시 `sessions` 문서도 읽고, 복원에 성공하면
    신규 구조로 옮긴 뒤 원문 개인정보를 제거한다(P0-3 · P0-4).

    device_id 는 쿠키가 아니라 `__session` 안에 있다(Firebase Hosting 제약).
    """
    if session.get("credentials") and session.get("user_key"):
        return
    if (
        request.path in _NO_RESTORE_PATHS
        or request.path.startswith("/static/")
        # /privacy/history/<slug>, /terms/history 등 동적 하위 경로 포함
        or request.path.startswith("/privacy/")
        or request.path.startswith("/terms/")
    ):
        return
    if _get_fs_db() is None:
        return
    device_id = session.get("device_id")
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
    if ctx.get("scope_version", 1) < _OAUTH_SCOPE_VERSION:
        # 구버전 OAuth 범위(drive.metadata.readonly 포함)로 발급된 refresh
        # token 이다. 파괴적으로 삭제하지 않고 자동 복원만 중단해, 사용자가
        # 새 범위(drive.file)로 1회 재동의하도록 유도한다 (task-2026-08-004 §6.5).
        logger.info("device session has outdated oauth scope version; re-consent required")
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
    session["auth_at"] = auth_timestamp()
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

    # 쿠키 만료는 SESSION_REFRESH_EACH_REQUEST 가 요청마다 연장한다.
    # (연장하지 않으면 계속 사용 중인 사용자도 최초 로그인 90일 후 로그아웃된다)


@app.after_request
def prevent_cdn_caching(resp):
    """Firebase Hosting CDN 이 인증된 응답을 캐시하지 않도록 강제한다.

    커스텀 도메인은 CDN 을 경유하고, 백엔드에는 `__session` 만 전달되므로
    캐시 키를 신뢰할 수 없다. 정적 파일을 제외한 모든 응답을 캐시 금지로
    표시해 다른 사용자에게 노출되는 사고를 막는다(조치안 개정 2판 2.5).
    """
    if request.path.startswith("/static/"):
        return resp
    resp.headers.setdefault("Cache-Control", "private, no-store")
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
from routes.site import site_bp

app.register_blueprint(auth_bp)
app.register_blueprint(sheet_bp)
app.register_blueprint(main_bp)
app.register_blueprint(item_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(site_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=IS_DEV)
