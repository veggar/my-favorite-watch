import os
import json
from flask import Blueprint, redirect, request, session, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

auth_bp = Blueprint("auth", __name__)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080/auth/callback"],
    }
}


def _build_flow():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="http://localhost:8080/auth/callback",
    )
    return flow


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
    return redirect(authorization_url)


@auth_bp.route("/auth/callback")
def auth_callback():
    if "oauth_state" not in session or request.args.get("state") != session["oauth_state"]:
        return redirect(url_for("auth.login"))

    flow = _build_flow()
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

    # 사용자 정보 조회
    import googleapiclient.discovery
    service = googleapiclient.discovery.build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()
    session["user"] = {
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }

    # 시트 연결 여부 확인
    if session.get("sheet_id"):
        return redirect(url_for("main.index"))
    return redirect(url_for("sheet.connect"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def get_credentials():
    """세션에서 Google 인증 정보를 복원."""
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
    # 만료된 토큰 갱신
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        session["credentials"]["token"] = creds.token
    return creds


def login_required(f):
    """로그인 필요 데코레이터."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or "credentials" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def sheet_required(f):
    """시트 연결 필요 데코레이터."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or "credentials" not in session:
            return redirect(url_for("auth.login"))
        if not session.get("sheet_id"):
            return redirect(url_for("sheet.connect"))
        return f(*args, **kwargs)
    return decorated
