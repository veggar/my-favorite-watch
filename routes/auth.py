import os
import secrets
from functools import wraps

from flask import Blueprint, make_response, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests

from services.firestore_session import (
    save_session,
    delete_session,
    lookup_saved_sheet,
    apply_sheet_to_session,
    get_refresh_token,
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
    worker_payload,
)

auth_bp = Blueprint("auth", __name__)

REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8090/auth/callback")


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


@auth_bp.route("/login")
def login():
    from flask import render_template
    return render_template("login.html")


@auth_bp.route("/auth/google")
def google_login():
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
    if "oauth_state" not in session or request.args.get("state") != session["oauth_state"]:
        return redirect(url_for("auth.login"))

    flow = _build_flow()
    code_verifier = session.pop("code_verifier", None)
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    # 세션에는 access token 과 만료 시각만 저장한다.
    # client_secret / refresh_token 은 Flask 세션 쿠키가 암호화되지 않으므로
    # 절대 담지 않는다. (security.md "Sanitization")
    session["credentials"] = session_payload(credentials)

    import googleapiclient.discovery
    svc = googleapiclient.discovery.build("oauth2", "v2", credentials=credentials)
    user_info = svc.userinfo().get().execute()
    session["user"] = {
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }

    # Firestore에 refresh_token 저장 + device_id 쿠키 발급
    device_id = request.cookies.get("device_id") or secrets.token_urlsafe(32)

    # 세션 만료 후 재로그인한 경우 이전에 연결한 시트 정보를 복원하여
    # 시트를 다시 설정하도록 요구하지 않는다.
    if not session.get("sheet_id"):
        apply_sheet_to_session(
            lookup_saved_sheet(device_id, session["user"].get("email", ""))
        )

    save_session(device_id, credentials.refresh_token, session["user"])

    dest = url_for("main.index") if session.get("sheet_id") else url_for("sheet.connect")
    resp = make_response(redirect(dest))
    resp.set_cookie(
        "device_id",
        device_id,
        max_age=60 * 60 * 24 * 90,  # 90일
        httponly=True,
        samesite="Lax",
        secure=not (os.environ.get("APP_ENV", "production").lower() in ("development", "dev", "local")),
    )
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    device_id = request.cookies.get("device_id")
    delete_session(device_id)
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


def export_credentials_for_worker() -> dict:
    """동일 프로세스 내 워커 스레드에 넘길 자격증명 직렬화.

    ⚠️ client_secret 이 포함된다. 세션 · 쿠키 · 로그 · 응답에 넣지 말 것.
    """
    creds = get_credentials()
    if creds is None:
        return {}
    if not creds.refresh_token:
        # 갱신 가능하도록 refresh_token 을 함께 실어 보낸다(메모리 전달 전용).
        refresh_token = get_refresh_token(request.cookies.get("device_id"))
        if refresh_token:
            creds = credentials_from_session(session.get("credentials", {}), refresh_token)
    return worker_payload(creds)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or "credentials" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def sheet_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or "credentials" not in session:
            return redirect(url_for("auth.login"))
        if not session.get("sheet_id"):
            return redirect(url_for("sheet.connect"))
        return f(*args, **kwargs)
    return decorated
