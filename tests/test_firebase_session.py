"""P0-5 통합 회귀 테스트 — Firebase Hosting 환경의 세션 동작.

검증 대상 (조치안 개정 2판 5.1)

- 응답이 `__session` 쿠키 **하나만** 발급한다
- 로그인 시 device_id · user_key · auth_at 이 세션에 채워진다
- 같은 브라우저는 재로그인해도 같은 device_id 를 유지한다
- auth_at 이 만료되면 credentials 만 폐기되고 기기 계층은 남는다
- 폐기 후 Firestore refresh_token 으로 세션이 재구성된다
- 정적 파일 외 응답은 CDN 에 캐시되지 않는다

실행: python3 -m pytest -q
"""
from datetime import datetime, timedelta, timezone

import pytest

import app as app_module
from routes import auth as auth_module
from services import firestore_session as fs
from fake_firestore import DELETE_FIELD, FakeFirestoreClient

USER_A = "v1_user-key-aaa"
USER_B = "v1_user-key-bbb"
EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"


@pytest.fixture
def db(monkeypatch):
    client = FakeFirestoreClient()
    monkeypatch.setattr(fs, "_db", client)
    monkeypatch.setattr(fs, "_DELETE_FIELD", DELETE_FIELD)
    return client


@pytest.fixture
def client(db):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


class _FakeCredentials:
    def __init__(self, refresh_token="refresh-token", token="access-token"):
        self.token = token
        self.expiry = None
        self.refresh_token = refresh_token
        self.id_token = "id-token"


class _FakeFlow:
    def __init__(self, credentials):
        self.credentials = credentials
        self.code_verifier = None

    def fetch_token(self, authorization_response=None):
        return None


def _login(client, monkeypatch, user_key=USER_A, email=EMAIL_A, refresh_token="refresh-token"):
    monkeypatch.setattr(
        auth_module, "_build_flow", lambda: _FakeFlow(_FakeCredentials(refresh_token))
    )
    monkeypatch.setattr(
        auth_module,
        "user_key_from_id_token",
        lambda raw, audience: (user_key, {"email": email, "name": "표시이름", "picture": ""}),
    )
    with client.session_transaction() as sess:
        sess["oauth_state"] = "state-123"
    return client.get("/auth/callback?state=state-123&code=auth-code")


# ── 쿠키 발급 ──────────────────────────────────────────────────────────────

def test_login_sets_only_the_session_cookie(client, monkeypatch, db):
    resp = _login(client, monkeypatch)

    cookies = resp.headers.getlist("Set-Cookie")
    assert len(cookies) == 1, f"쿠키가 하나여야 한다: {cookies}"
    assert cookies[0].startswith("__session=")
    assert "device_id=" not in cookies[0]


def test_login_populates_device_and_auth_fields(client, monkeypatch, db):
    _login(client, monkeypatch)

    with client.session_transaction() as sess:
        assert sess["device_id"]
        assert sess["user_key"] == USER_A
        assert sess["auth_at"]


def test_device_id_is_stable_across_relogin(client, monkeypatch, db):
    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        first = sess["device_id"]

    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        assert sess["device_id"] == first

    # 같은 기기이므로 Firestore 문서도 하나만 남는다
    assert len(db.docs(fs.DEVICE_SESSIONS_COLLECTION)) == 1


def test_separate_clients_get_separate_device_ids(monkeypatch, db):
    app_module.app.config["TESTING"] = True
    client_a = app_module.app.test_client()
    client_b = app_module.app.test_client()

    _login(client_a, monkeypatch, refresh_token="refresh-a")
    _login(client_b, monkeypatch, refresh_token="refresh-b")

    with client_a.session_transaction() as sess:
        device_a, key_a = sess["device_id"], sess["user_key"]
    with client_b.session_transaction() as sess:
        device_b, key_b = sess["device_id"], sess["user_key"]

    assert device_a != device_b
    assert key_a == key_b == USER_A
    assert len(db.docs(fs.DEVICE_SESSIONS_COLLECTION)) == 2


def test_account_switch_keeps_device_but_replaces_user(client, monkeypatch, db):
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")
    _login(client, monkeypatch, USER_A, EMAIL_A)
    with client.session_transaction() as sess:
        device = sess["device_id"]

    resp = _login(client, monkeypatch, USER_B, EMAIL_B, refresh_token="refresh-b")

    assert resp.headers["Location"].endswith("/connect")
    with client.session_transaction() as sess:
        assert sess["device_id"] == device
        assert sess["user_key"] == USER_B
        assert not sess.get("sheet_id")
    assert db.docs(fs.DEVICE_SESSIONS_COLLECTION)[device]["user_key"] == USER_B


# ── 단기 계층 만료와 재구성 ────────────────────────────────────────────────

def _expire_auth(client):
    stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with client.session_transaction() as sess:
        sess["auth_at"] = stale


def test_stale_auth_drops_credentials_but_keeps_device_layer(client, monkeypatch, db):
    """만료 시 access token 계층만 사라지고 기기·사용자 식별은 남아야 한다."""
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")
    _login(client, monkeypatch)
    _expire_auth(client)

    # Firestore 재발급이 실패하도록 만들어 "폐기"만 관찰한다
    monkeypatch.setattr(
        app_module, "_restore_device_context", lambda device_id: None
    )
    client.get("/settings")

    with client.session_transaction() as sess:
        assert "credentials" not in sess
        assert sess["device_id"]
        assert sess["user_key"] == USER_A


def test_stale_auth_is_restored_from_stored_refresh_token(client, monkeypatch, db):
    """폐기 후 같은 요청에서 Firestore refresh_token 으로 재구성된다."""
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")
    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        old_auth_at = sess["auth_at"]
    _expire_auth(client)

    refreshed = _FakeCredentials(refresh_token="refresh-token", token="new-access-token")
    monkeypatch.setattr(
        app_module, "_build_credentials", lambda token, refresh_token: refreshed
    )
    monkeypatch.setattr(refreshed, "refresh", lambda request: None, raising=False)

    client.get("/settings")

    with client.session_transaction() as sess:
        assert sess["credentials"]["token"] == "new-access-token"
        assert sess["auth_at"] != old_auth_at
        assert sess["sheet_id"] == "sheet-a"


def test_session_without_auth_at_is_treated_as_stale(client, monkeypatch, db):
    """이전 스키마에서 넘어온 세션은 신선하지 않은 것으로 본다."""
    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        del sess["auth_at"]

    monkeypatch.setattr(app_module, "_restore_device_context", lambda device_id: None)
    client.get("/settings")

    with client.session_transaction() as sess:
        assert "credentials" not in sess


# ── CDN 캐시 안전 ──────────────────────────────────────────────────────────

def test_dynamic_responses_are_not_cacheable(client):
    resp = client.get("/login")
    assert resp.headers["Cache-Control"] == "private, no-store"


def test_static_files_keep_their_own_cache_policy(client):
    resp = client.get("/static/css/style.css")
    assert resp.headers.get("Cache-Control") != "private, no-store"


# ── 로그아웃 ───────────────────────────────────────────────────────────────

def test_device_logout_removes_only_this_device(client, monkeypatch, db):
    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        device = sess["device_id"]
        csrf = sess["_csrf_token"] = "csrf-token"
    fs.save_device_session("other-device", USER_A, "refresh-other")

    client.post("/logout", data={"csrf_token": csrf})

    assert device not in db.docs(fs.DEVICE_SESSIONS_COLLECTION)
    assert "other-device" in db.docs(fs.DEVICE_SESSIONS_COLLECTION)
    with client.session_transaction() as sess:
        assert "user_key" not in sess


def test_full_logout_removes_every_device(client, monkeypatch, db):
    _login(client, monkeypatch)
    with client.session_transaction() as sess:
        csrf = sess["_csrf_token"] = "csrf-token"
    fs.save_device_session("other-device", USER_A, "refresh-other")

    client.post("/logout-all", data={"csrf_token": csrf})

    assert db.docs(fs.DEVICE_SESSIONS_COLLECTION) == {}
