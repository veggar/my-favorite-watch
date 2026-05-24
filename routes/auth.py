import os
import secrets
from functools import wraps

from flask import Blueprint, make_response, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

from services.firestore_session import save_session, delete_session

auth_bp = Blueprint("auth", __name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/spreadsheets",
    # drive.readonly → metadata.readonly 로 최소 권한 원칙 적용
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]

REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8090/auth/callback")


def _build_flow():
    client_config = {
        "web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
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
    session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
    }

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
    """세션에서 Google 인증 정보를 복원하고 만료 시 갱신."""
    if "credentials" not in session:
        return None
    creds_data = session["credentials"]
    creds = Credentials(
        token=creds_data["token"],
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        session["credentials"]["token"] = creds.token
    return creds


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
