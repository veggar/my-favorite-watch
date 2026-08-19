"""P0-1 · P0-3 · P0-4 회귀 테스트 — 멀티 디바이스 · 계정 격리 · 개인정보 최소화.

조치안 7장 완료 기준을 코드 수준에서 고정한다.

- 7.1 인증·도메인: state 누락/불일치 구분, 공급자 오류 정규화, canonical host
- 7.2 멀티 디바이스: device_id 는 다르고 user_key 는 같다, 기기별 로그아웃
- 7.3 계정 분리: 같은 브라우저에서 계정을 바꿔도 이전 시트가 노출되지 않는다
- 7.4 개인정보 최소화: Firestore 문서에 이메일 · 이름 · 프로필 원문이 없다

실행: pytest -q
"""
import os

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("USER_KEY_HMAC_SECRET", "t" * 48)

import app as app_module  # noqa: E402
from routes import auth as auth_module  # noqa: E402
from services import firestore_session as fs  # noqa: E402
from fake_firestore import DELETE_FIELD, FakeFirestoreClient  # noqa: E402

USER_A = "v1_user-key-aaa"
USER_B = "v1_user-key-bbb"
EMAIL_A = "alice@example.com"
EMAIL_B = "bob@example.com"

PII_KEYS = ("email", "user", "name", "picture", "given_name", "family_name")


@pytest.fixture
def db(monkeypatch):
    client = FakeFirestoreClient()
    monkeypatch.setattr(fs, "_db", client)
    monkeypatch.setattr(fs, "_DELETE_FIELD", DELETE_FIELD)
    return client


@pytest.fixture
def app_ctx():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_request_context("/"):
        yield


def assert_no_pii(document: dict):
    for key in PII_KEYS:
        assert key not in document, f"원문 개인정보 필드가 저장됐다: {key}"
    for value in document.values():
        if isinstance(value, str):
            assert "@" not in value, f"이메일로 보이는 값이 저장됐다: {value}"


# ── 7.2 멀티 디바이스 ──────────────────────────────────────────────────────

def test_two_devices_share_one_user_key_and_sheet(db):
    fs.save_device_session("device-a", USER_A, "refresh-a")
    fs.save_device_session("device-b", USER_A, "refresh-b")
    fs.save_user_sheet(USER_A, "sheet-1", "내 시트", "작품목록")

    a = fs.get_device_session("device-a")
    b = fs.get_device_session("device-b")

    assert a["user_key"] == b["user_key"] == USER_A
    assert a["refresh_token"] != b["refresh_token"]
    assert len(db.docs(fs.USERS_COLLECTION)) == 1
    assert fs.get_user_config(USER_A)["sheet_id"] == "sheet-1"


def test_device_logout_keeps_other_devices(db):
    fs.save_device_session("device-a", USER_A, "refresh-a")
    fs.save_device_session("device-b", USER_A, "refresh-b")

    fs.delete_device_session("device-a")

    assert fs.get_device_session("device-a") is None
    assert fs.get_device_session("device-b")["refresh_token"] == "refresh-b"


def test_full_logout_removes_every_device_of_the_user(db):
    fs.save_device_session("device-a", USER_A, "refresh-a")
    fs.save_device_session("device-b", USER_A, "refresh-b")
    fs.save_device_session("device-c", USER_B, "refresh-c")

    removed = fs.delete_all_device_sessions(USER_A)

    assert removed == 2
    assert fs.get_device_session("device-a") is None
    assert fs.get_device_session("device-b") is None
    assert fs.get_device_session("device-c") is not None


def test_full_logout_also_clears_legacy_devices(db):
    db.docs(fs.LEGACY_COLLECTION)["legacy-device"] = {
        "user_key": USER_A,
        "refresh_token": "legacy-token",
    }
    fs.save_device_session("device-a", USER_A, "refresh-a")

    assert fs.delete_all_device_sessions(USER_A) == 2
    assert "legacy-device" not in db.docs(fs.LEGACY_COLLECTION)


def test_device_session_has_ttl_field(db):
    fs.save_device_session("device-a", USER_A, "refresh-a")
    doc = fs.get_device_session("device-a")
    delta = doc["expires_at"] - doc["created_at"]
    assert round(delta.total_seconds() / 86400) == fs.DEVICE_SESSION_TTL_DAYS


# ── 7.4 개인정보 최소화 ────────────────────────────────────────────────────

def test_device_session_stores_no_personal_data(db):
    fs.save_device_session("device-a", USER_A, "refresh-a")
    assert_no_pii(fs.get_device_session("device-a"))


def test_user_document_stores_no_personal_data(db):
    fs.save_user_sheet(USER_A, "sheet-1", "내 시트", "작품목록")
    assert_no_pii(fs.get_user_config(USER_A))


def test_user_sheet_is_not_overwritten_with_empty_values(db, app_ctx):
    """재로그인 직후 세션이 비어 있어도 기존 연결을 지우면 안 된다."""
    fs.save_user_sheet(USER_A, "sheet-1", "내 시트", "작품목록")
    fs.update_sheet_from_session(USER_A)  # 세션에 sheet_id 없음
    assert fs.get_user_config(USER_A)["sheet_id"] == "sheet-1"


def test_disconnect_clears_stored_sheet(db):
    fs.save_user_sheet(USER_A, "sheet-1", "내 시트", "작품목록")
    fs.clear_user_sheet(USER_A)
    assert fs.get_user_config(USER_A)["sheet_id"] == ""


# ── P0-4 레거시 마이그레이션 ──────────────────────────────────────────────

def _seed_legacy(db, device_id, email, sheet_id="legacy-sheet"):
    from datetime import datetime, timezone

    db.docs(fs.LEGACY_COLLECTION)[device_id] = {
        "email": email,
        "user": {"email": email, "name": "홍길동", "picture": "https://example.com/p.png"},
        "refresh_token": f"token-{device_id}",
        "sheet_id": sheet_id,
        "sheet_title": "레거시 시트",
        "worksheet_name": "작품목록",
        "updated_at": datetime.now(timezone.utc),
    }


def test_legacy_sheet_is_migrated_and_scrubbed(db):
    _seed_legacy(db, "device-a", EMAIL_A)

    migrated = fs.migrate_legacy_user(USER_A, EMAIL_A)

    assert migrated["sheet_id"] == "legacy-sheet"
    assert fs.get_user_config(USER_A)["sheet_id"] == "legacy-sheet"

    legacy = db.docs(fs.LEGACY_COLLECTION)["device-a"]
    assert "email" not in legacy and "user" not in legacy
    assert legacy["user_key"] == USER_A
    assert legacy["migrated_at"] is not None
    # 아직 재로그인하지 않은 기기의 자동 복원을 위해 토큰은 남긴다.
    assert legacy["refresh_token"] == "token-device-a"


def test_migration_never_borrows_another_accounts_sheet(db):
    _seed_legacy(db, "device-a", EMAIL_A)

    assert fs.migrate_legacy_user(USER_B, EMAIL_B) is None
    assert fs.get_user_config(USER_B) is None
    # 다른 계정 문서는 손대지 않는다.
    assert db.docs(fs.LEGACY_COLLECTION)["device-a"]["email"] == EMAIL_A


def test_restore_context_prefers_new_structure(db):
    _seed_legacy(db, "device-a", EMAIL_A)
    fs.save_device_session("device-a", USER_A, "new-token")

    ctx = fs.restore_device_context("device-a")

    assert ctx == {"user_key": USER_A, "refresh_token": "new-token", "source": "device"}


def test_restore_context_falls_back_to_legacy(db):
    _seed_legacy(db, "device-a", EMAIL_A)
    fs.migrate_legacy_user(USER_A, EMAIL_A)  # user_key 만 기록된 상태

    ctx = fs.restore_device_context("device-a")

    assert ctx["source"] == "legacy"
    assert ctx["user_key"] == USER_A


def test_legacy_device_upgrade_moves_token_to_new_collection(db):
    _seed_legacy(db, "device-a", EMAIL_A)
    fs.migrate_legacy_user(USER_A, EMAIL_A)

    fs.upgrade_legacy_device("device-a", USER_A, "token-device-a")

    assert fs.get_device_session("device-a")["user_key"] == USER_A
    assert_no_pii(fs.get_device_session("device-a"))


# ── 7.1 인증 실패 진단 ────────────────────────────────────────────────────

@pytest.fixture
def client(db):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_missing_state_is_distinguished_from_mismatch(client):
    """쿠키는 도달했는데 state 만 없는 경우."""
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "seed"  # 세션 쿠키만 만들고 oauth_state 는 비운다
    resp = client.get("/auth/callback?state=abc&code=x")
    assert resp.status_code == 302
    assert "e=AUTH_STATE_MISSING" in resp.headers["Location"]


def test_absent_session_cookie_is_reported_separately(client):
    """세션 쿠키 자체가 오지 않으면 전달 경로 문제로 분기해야 한다.

    Firebase Hosting 은 `__session` 외의 쿠키를 백엔드로 전달하지 않는다.
    이 코드가 관측되면 애플리케이션이 아니라 Hosting 구성을 봐야 한다.
    """
    resp = client.get("/auth/callback?state=abc&code=x")
    assert "e=AUTH_COOKIE_BLOCKED" in resp.headers["Location"]


def test_state_mismatch_returns_its_own_code(client):
    with client.session_transaction() as sess:
        sess["oauth_state"] = "expected-state"
    resp = client.get("/auth/callback?state=wrong-state&code=x")
    assert "e=AUTH_STATE_MISMATCH" in resp.headers["Location"]


def test_provider_error_is_normalized(client):
    resp = client.get("/auth/callback?error=access_denied&error_description=leaky+detail")
    assert "e=AUTH_DENIED" in resp.headers["Location"]

    resp = client.get("/auth/callback?error=server_error")
    assert "e=AUTH_PROVIDER" in resp.headers["Location"]


def test_login_page_shows_traceable_error_code(client):
    body = client.get("/login?e=AUTH_STATE_MISMATCH").get_data(as_text=True)
    assert "AUTH_STATE_MISMATCH" in body
    assert auth_module.AUTH_ERROR_MESSAGES["AUTH_STATE_MISMATCH"] in body


def test_unknown_error_code_is_not_reflected(client):
    """임의 문자열이 로그인 화면에 그대로 출력되지 않아야 한다(반사 XSS 방지)."""
    body = client.get("/login?e=<script>alert(1)</script>").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body


def test_session_without_user_key_requires_relogin(client):
    """이전 스키마의 잔여 세션은 보호된 페이지에 접근할 수 없다."""
    with client.session_transaction() as sess:
        sess["credentials"] = {"token": "t", "expiry": ""}
        sess["user"] = {"email": EMAIL_A}
    resp = client.get("/settings")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_canonical_host_redirect_in_production(monkeypatch, client):
    monkeypatch.setattr(app_module, "IS_DEV", False)
    monkeypatch.setattr(auth_module, "REDIRECT_URI", "https://mfw.example.com/auth/callback")

    resp = client.get("/login", base_url="https://service-abc.a.run.app")

    assert resp.status_code == 308
    assert resp.headers["Location"] == "https://mfw.example.com/login"


def test_canonical_host_is_not_enforced_in_development(client):
    resp = client.get("/login", base_url="http://localhost:8090")
    assert resp.status_code == 200


# ── 7.3 계정 분리 (콜백 전 구간) ──────────────────────────────────────────

class _FakeCredentials:
    def __init__(self, refresh_token="refresh-token"):
        self.token = "access-token"
        self.expiry = None
        self.refresh_token = refresh_token
        self.id_token = "id-token"


class _FakeFlow:
    def __init__(self, credentials):
        self.credentials = credentials
        self.code_verifier = None

    def fetch_token(self, authorization_response=None):
        return None


def _login(client, monkeypatch, user_key, email, refresh_token="refresh-token"):
    monkeypatch.setattr(
        auth_module, "_build_flow", lambda: _FakeFlow(_FakeCredentials(refresh_token))
    )
    monkeypatch.setattr(
        auth_module,
        "user_key_from_id_token",
        lambda raw, audience: (
            user_key,
            {"email": email, "name": "표시이름", "picture": "https://example.com/p.png"},
        ),
    )
    with client.session_transaction() as sess:
        sess["oauth_state"] = "state-123"
    return client.get("/auth/callback?state=state-123&code=auth-code")


def test_successful_login_stores_device_session_without_pii(client, monkeypatch, db):
    resp = _login(client, monkeypatch, USER_A, EMAIL_A)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/connect")

    devices = db.docs(fs.DEVICE_SESSIONS_COLLECTION)
    assert len(devices) == 1
    stored = next(iter(devices.values()))
    assert stored["user_key"] == USER_A
    assert_no_pii(stored)


def test_saved_sheet_is_restored_on_relogin(client, monkeypatch, db):
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")

    resp = _login(client, monkeypatch, USER_A, EMAIL_A)

    assert resp.headers["Location"].endswith("/")
    with client.session_transaction() as sess:
        assert sess["sheet_id"] == "sheet-a"
        assert sess["user_key"] == USER_A


def test_account_switch_on_same_browser_isolates_sheets(client, monkeypatch, db):
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")
    _login(client, monkeypatch, USER_A, EMAIL_A)

    resp = _login(client, monkeypatch, USER_B, EMAIL_B, refresh_token="refresh-b")

    # 계정 B 는 A 의 시트를 이어받지 않고 연결 화면으로 이동한다.
    assert resp.headers["Location"].endswith("/connect")
    with client.session_transaction() as sess:
        assert sess["user_key"] == USER_B
        assert not sess.get("sheet_id")

    devices = list(db.docs(fs.DEVICE_SESSIONS_COLLECTION).values())
    assert len(devices) == 1
    assert devices[0]["user_key"] == USER_B
    assert devices[0]["refresh_token"] == "refresh-b"
    # A 의 사용자 문서는 그대로 남는다(다른 기기에서 계속 사용).
    assert fs.get_user_config(USER_A)["sheet_id"] == "sheet-a"


def test_login_without_refresh_token_leaves_no_stale_device_session(client, monkeypatch, db):
    _login(client, monkeypatch, USER_A, EMAIL_A)
    _login(client, monkeypatch, USER_B, EMAIL_B, refresh_token="")

    assert db.docs(fs.DEVICE_SESSIONS_COLLECTION) == {}


def test_oauth_start_blocked_on_non_canonical_host(monkeypatch, client):
    """운영 리디렉션이 꺼진 상태에서도 시작 host 가 다르면 로그인 루프를 만들지 않는다."""
    monkeypatch.setattr(auth_module, "REDIRECT_URI", "https://mfw.example.com/auth/callback")

    resp = client.get("/auth/google", base_url="http://localhost:8090")

    assert resp.status_code == 302
    assert "e=AUTH_HOST" in resp.headers["Location"]
