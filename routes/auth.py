import logging
import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests

from services.firestore_session import (
    apply_sheet_to_session,
    delete_all_device_sessions,
    delete_device_session,
    get_device_session,
    get_refresh_token,
    get_user_config,
    migrate_legacy_user,
    save_device_session,
    update_refresh_token,
)
from services.google_credentials import (
    SCOPES,
    TOKEN_URI,
    AUTH_URI,
    client_id as _client_id,
    client_secret as _client_secret,
    credentials_from_session,
    session_payload,
)
from services.user_identity import (
    USER_KEY_VERSION,
    UserIdentityError,
    user_key_from_id_token,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8090/auth/callback")

# 장기 로그인 유지 기간. Flask 세션(단기)이 만료돼도 이 쿠키와 Firestore
# refresh_token 으로 세션을 자동 복원하므로, 사용자가 체감하는 로그인 유지
# 기간은 이 값이 기준이 된다.
DEVICE_ID_MAX_AGE = 60 * 60 * 24 * 90  # 90일

# ── 인증 실패 코드 (P0-1) ─────────────────────────────────────────────────
# 화면에는 원인별 안내 문구와 추적용 코드만 노출하고, 실제 원인(예외 타입 ·
# state 불일치 여부)은 서버 로그에만 남긴다. OAuth code 와 state 값 자체는
# 어느 쪽에도 기록하지 않는다(security.md Sanitization).
AUTH_ERROR_MESSAGES = {
    "AUTH_STATE_MISSING": "로그인 요청 정보가 만료되었습니다. 다시 로그인해주세요.",
    "AUTH_STATE_MISMATCH": "로그인 요청을 확인하지 못했습니다. 다시 로그인해주세요.",
    "AUTH_DENIED": "Google 계정 접근이 승인되지 않았습니다. 다시 시도해주세요.",
    "AUTH_PROVIDER": "Google 인증 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "AUTH_TOKEN": "인증 토큰을 발급받지 못했습니다. 잠시 후 다시 시도해주세요.",
    "AUTH_IDENTITY": "계정 확인에 실패했습니다. 잠시 후 다시 시도해주세요.",
    "AUTH_HOST": "잘못된 주소로 접속했습니다. 공식 주소에서 다시 시도해주세요.",
}


def canonical_host() -> str:
    """운영에서 허용하는 공식 host. `REDIRECT_URI` 를 단일 기준으로 삼는다."""
    return urlsplit(REDIRECT_URI).netloc


def _cookie_secure() -> bool:
    return os.environ.get("APP_ENV", "production").lower() not in ("development", "dev", "local")


def set_device_cookie(resp, device_id: str) -> None:
    """device_id 쿠키를 발급/연장한다. 만료는 마지막 사용 시점 기준으로 갱신된다."""
    resp.set_cookie(
        "device_id",
        device_id,
        max_age=DEVICE_ID_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=_cookie_secure(),
    )


def _build_flow():
    client_config = {
        "web": {
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [REDIRECT_URI],
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)


def _auth_failed(code: str):
    """추적 가능한 코드와 함께 로그인 화면으로 되돌린다."""
    return redirect(url_for("auth.login", e=code))


@auth_bp.route("/login")
def login():
    code = request.args.get("e", "")
    message = AUTH_ERROR_MESSAGES.get(code)
    return render_template(
        "login.html",
        error=message,
        error_code=code if message else "",
    )


@auth_bp.route("/auth/google")
def google_login():
    # 콜백은 REDIRECT_URI 의 host 로만 돌아온다. 다른 host 에서 시작하면
    # state 를 담은 세션 쿠키가 콜백 요청에 실리지 않아 로그인 루프가 된다.
    expected_host = canonical_host()
    if expected_host and request.host != expected_host:
        logger.warning("OAuth start blocked: request host does not match REDIRECT_URI host")
        return _auth_failed("AUTH_HOST")

    flow = _build_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    if hasattr(flow, "code_verifier") and flow.code_verifier:
        session["code_verifier"] = flow.code_verifier
    elif hasattr(flow.oauth2session, "_code_verifier"):
        session["code_verifier"] = flow.oauth2session._code_verifier
    return redirect(authorization_url)


@auth_bp.route("/auth/callback")
def auth_callback():
    # ── 1. 공급자 오류 정규화 ──────────────────────────────────────────
    provider_error = request.args.get("error")
    if provider_error:
        # error_description 은 그대로 노출하지 않고 서버 로그에만 남긴다.
        logger.warning(
            "OAuth provider error: %s", "access_denied"
            if provider_error == "access_denied" else "other"
        )
        return _auth_failed(
            "AUTH_DENIED" if provider_error == "access_denied" else "AUTH_PROVIDER"
        )

    # ── 2. state 검증 (누락과 불일치를 구분) ──────────────────────────
    expected_state = session.pop("oauth_state", None)
    if not expected_state:
        logger.warning("OAuth callback rejected: oauth_state missing in session")
        return _auth_failed("AUTH_STATE_MISSING")
    if not secrets.compare_digest(request.args.get("state", ""), expected_state):
        logger.warning("OAuth callback rejected: oauth_state mismatch")
        return _auth_failed("AUTH_STATE_MISMATCH")

    # ── 3. 토큰 교환 ──────────────────────────────────────────────────
    flow = _build_flow()
    code_verifier = session.pop("code_verifier", None)
    if code_verifier:
        flow.code_verifier = code_verifier
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        # 예외 문자열에는 code · client_secret 이 포함될 수 있어 타입만 남긴다.
        logger.warning("OAuth token exchange failed (%s)", type(e).__name__)
        return _auth_failed("AUTH_TOKEN")

    credentials = flow.credentials

    # ── 4. ID Token 검증 → HMAC 사용자 키 (P0-2) ──────────────────────
    try:
        user_key, claims = user_key_from_id_token(
            getattr(credentials, "id_token", None), _client_id()
        )
    except UserIdentityError as e:
        # UserIdentityError 메시지에는 sub · 이메일 · 토큰이 포함되지 않는다.
        logger.warning("User identity resolution failed: %s", e)
        return _auth_failed("AUTH_IDENTITY")

    # 계정 전환 시 이전 계정의 시트·설정이 남지 않도록 세션을 비우고 시작한다.
    session.clear()
    # permanent 를 지정하지 않으면 브라우저 종료 시 사라지는 세션 쿠키가 되어
    # PERMANENT_SESSION_LIFETIME 이 적용되지 않는다.
    session.permanent = True
    # 세션에는 access token 과 만료 시각만 저장한다.
    # client_secret / refresh_token 은 Flask 세션 쿠키가 암호화되지 않으므로
    # 절대 담지 않는다. (security.md "Sanitization")
    session["credentials"] = session_payload(credentials)
    session["user_key"] = user_key
    session["user_key_version"] = USER_KEY_VERSION
    # 표시용 이름 · 프로필 이미지는 검증된 ID Token 클레임에서 가져오며
    # Flask 세션 수명 안에서만 사용한다(Firestore 에 저장하지 않는다).
    session["user"] = {
        "name": claims.get("name", ""),
        "picture": claims.get("picture", ""),
        "email": claims.get("email", ""),
    }

    # ── 5. 사용자 시트 설정 복원 (+ 레거시 1회 마이그레이션, P0-4) ────
    config = get_user_config(user_key)
    if config is None:
        # 신규 user_key 문서가 없을 때만, 현재 로그인 이메일과 정확히
        # 일치하는 레거시 문서를 한 번 조회해 시트 설정을 인수인계한다.
        config = migrate_legacy_user(user_key, claims.get("email", ""))
    apply_sheet_to_session(config)

    # ── 6. 기기 세션 저장 ─────────────────────────────────────────────
    device_id = request.cookies.get("device_id") or secrets.token_urlsafe(32)
    existing = get_device_session(device_id)
    if existing and existing.get("user_key") and existing["user_key"] != user_key:
        # 같은 브라우저에서 계정이 바뀐 경우. 이전 계정의 refresh token 이
        # 남아 자동 복원되지 않도록 먼저 제거한다(조치안 7.3).
        logger.info("device session replaced due to account switch")
        delete_device_session(device_id)

    if credentials.refresh_token:
        if not save_device_session(device_id, user_key, credentials.refresh_token):
            # 저장 실패로 로그인 자체를 막지는 않는다(조치안 9. 롤백 원칙).
            flash("자동 로그인 정보를 저장하지 못했습니다. 다음 접속 시 다시 로그인이 필요할 수 있습니다.", "error")
    else:
        # refresh token 이 없으면 자동 복원이 불가능하다. 이전 계정 문서가
        # 남아 잘못 복원되는 것을 막기 위해 기기 문서를 비워둔다.
        logger.warning("no refresh_token in token response; device session not stored")
        delete_device_session(device_id)

    # ── 7. 목적지 기록 (P0-1) ─────────────────────────────────────────
    has_sheet = bool(session.get("sheet_id"))
    logger.info("oauth callback success → %s", "/" if has_sheet else "/connect")
    dest = url_for("main.index") if has_sheet else url_for("sheet.connect")
    resp = make_response(redirect(dest))
    set_device_cookie(resp, device_id)
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """현재 기기만 로그아웃한다. 다른 기기 세션은 유지된다."""
    device_id = request.cookies.get("device_id")
    delete_device_session(device_id)
    session.clear()
    resp = make_response(redirect(url_for("auth.login")))
    resp.delete_cookie("device_id")
    return resp


@auth_bp.route("/logout-all", methods=["POST"])
def logout_all():
    """전체 로그아웃 — 같은 계정의 모든 기기 세션을 무효화한다."""
    user_key = session.get("user_key")
    if user_key:
        count = delete_all_device_sessions(user_key)
        logger.info("full logout: %d device session(s) removed", count)
    session.clear()
    resp = make_response(redirect(url_for("auth.login")))
    resp.delete_cookie("device_id")
    return resp


def get_credentials():
    """세션의 access token 으로 Credentials 를 재구성하고 만료 시 갱신한다.

    refresh_token 은 세션이 아니라 Firestore 에 있으므로, 갱신이 실제로
    필요한 시점에만 device_id 로 조회한다(요청마다 조회하지 않는다).
    """
    creds_data = session.get("credentials")
    if not creds_data:
        return None

    creds = credentials_from_session(creds_data)
    if creds.token and not creds.expired:
        return creds

    device_id = request.cookies.get("device_id")
    refresh_token = get_refresh_token(device_id)
    if not refresh_token:
        # Firestore 미구성(로컬 개발) 등으로 갱신이 불가능한 경우.
        # 만료된 토큰 그대로 반환하면 API 호출이 실패하고 전역 에러 핸들러가
        # 로그인 화면으로 유도한다.
        return creds

    creds = credentials_from_session(creds_data, refresh_token)
    creds.refresh(google.auth.transport.requests.Request())
    session["credentials"] = session_payload(creds)
    if creds.refresh_token and creds.refresh_token != refresh_token:
        update_refresh_token(device_id, creds.refresh_token)
    return creds


def _is_authenticated() -> bool:
    """user_key 가 없는 세션은 이전 스키마의 잔여 세션이므로 재로그인시킨다."""
    return bool(session.get("credentials")) and bool(session.get("user_key"))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_authenticated():
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def sheet_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_authenticated():
            return redirect(url_for("auth.login"))
        if not session.get("sheet_id"):
            return redirect(url_for("sheet.connect"))
        return f(*args, **kwargs)
    return decorated
