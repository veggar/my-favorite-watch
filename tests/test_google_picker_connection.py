"""task-2026-08-004 회귀 테스트 — Google Picker · drive.file 전환.

검증 항목 (계획 문서 §8.1)

1. OAuth 범위: `drive.file` 포함, `drive.metadata.readonly` 미포함
2. 서버 코드에 Drive 전체 검색(`drive.files().list` · `find_spreadsheet_by_name`)이 없음
3. `/connect` 가 자동 검색을 호출하지 않고 세 가지 연결 경로를 제공함
4. Picker 미설정 환경에서도 URL 연결 · 새 시트 생성 폼이 동작함
5. `POST /connect/use-picked` 의 인증 · CSRF · 입력 검증 · 오류 정제
6. 클라이언트가 보낸 제목 대신 서버 조회 제목을 저장함
7. Picker 브라우저 설정에 서버 세션 토큰이 노출되지 않음
8. scope version — 구버전 refresh token 은 자동 복원되지 않음

실행: python3 -m pytest -q
"""
import re
from pathlib import Path

import pytest

import app as app_module
from routes import sheet as sheet_module
from services import firestore_session as fs
from services.google_credentials import OAUTH_SCOPE_VERSION, PICKER_SCOPE, SCOPES
from services.session_state import auth_timestamp
from fake_firestore import DELETE_FIELD, FakeFirestoreClient

ROOT = Path(__file__).resolve().parent.parent

USER_A = "v1_user-key-aaa"
CSRF = "csrf-token-for-tests"
VALID_SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcd"


# ── 픽스처 ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def logged_in(client):
    """로그인 상태의 테스트 클라이언트 (Firestore 미구성 → 자동 복원 없음)."""
    with client.session_transaction() as sess:
        sess["credentials"] = {"token": "ya29.server-session-token", "expiry": ""}
        sess["user_key"] = USER_A
        sess["auth_at"] = auth_timestamp()
        sess["_csrf_token"] = CSRF
        sess["user"] = {"name": "표시이름", "picture": "", "email": ""}
    return client


@pytest.fixture
def db(monkeypatch):
    fake = FakeFirestoreClient()
    monkeypatch.setattr(fs, "_db", fake)
    monkeypatch.setattr(fs, "_DELETE_FIELD", DELETE_FIELD)
    return fake


def _json_post(client, url, body, csrf=CSRF):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return client.post(url, json=body, headers=headers)


def _mock_attach_success(monkeypatch, title="서버가 조회한 제목"):
    """Sheets API 검증 경로를 성공으로 모킹한다."""
    monkeypatch.setattr(
        sheet_module, "get_credentials", lambda: object()
    )
    monkeypatch.setattr(
        sheet_module, "verify_sheet_access",
        lambda credentials, sheet_id: {"title": title, "worksheets": []},
    )
    monkeypatch.setattr(
        sheet_module, "ensure_worksheet",
        lambda credentials, sheet_id, name, headers: "1",
    )
    monkeypatch.setattr(
        sheet_module, "update_sheet_from_session", lambda user_key: True
    )


# ── 1 · 2. OAuth 범위와 서버 코드 ─────────────────────────────────────────

def test_scopes_use_drive_file_and_not_metadata_readonly():
    assert "https://www.googleapis.com/auth/drive.file" in SCOPES
    assert not any("drive.metadata.readonly" in s for s in SCOPES)
    assert not any("drive.readonly" in s for s in SCOPES)


def test_picker_scope_is_drive_file_only():
    assert PICKER_SCOPE == "https://www.googleapis.com/auth/drive.file"


def test_server_code_has_no_drive_wide_search():
    """서버 코드 어디에도 Drive 전체 검색 경로가 남아 있으면 안 된다.

    (주석에서 구 범위를 설명하는 것은 허용한다. 실제 요청 범위는
    test_scopes_use_drive_file_and_not_metadata_readonly 가 검증한다.)
    """
    for folder in ("services", "routes"):
        for path in (ROOT / folder).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "find_spreadsheet_by_name" not in text, \
                f"{path.name} 에 find_spreadsheet_by_name 이 남아 있다"
            # drive v3 files().list 호출 (자동 이름 검색) 금지
            assert not re.search(r"files\(\)\.list", text), \
                f"{path.name} 에 drive files().list 호출이 남아 있다"


def test_removed_endpoints_return_404(logged_in):
    assert _json_post(logged_in, "/connect/discover", {}).status_code == 404
    assert _json_post(
        logged_in, "/connect/use-found", {"sheet_id": VALID_SHEET_ID}
    ).status_code == 404


# ── 3 · 4. /connect 화면 ──────────────────────────────────────────────────

def test_connect_page_shows_three_paths_without_auto_discover(logged_in, monkeypatch):
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "AIza-test-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "641162137323")
    html = logged_in.get("/connect").get_data(as_text=True)

    # 자동 검색 잔재 없음
    assert "/connect/discover" not in html
    assert "step-found" not in html
    # 세 가지 경로
    assert 'id="btn-open-picker"' in html     # Drive 에서 선택
    assert 'id="form-connect"' in html        # URL 직접 연결
    assert 'id="form-create"' in html         # 새 시트 만들기
    assert "/connect/use-picked" in html


def test_connect_page_without_picker_config_keeps_url_and_create(logged_in, monkeypatch):
    monkeypatch.delenv("GOOGLE_PICKER_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_NUMBER", raising=False)
    html = logged_in.get("/connect").get_data(as_text=True)

    assert 'id="btn-open-picker"' not in html
    assert 'id="picker-config"' not in html
    assert 'id="form-connect"' in html
    assert 'id="form-create"' in html


def test_connect_page_never_exposes_server_session_token(logged_in, monkeypatch):
    """Picker 설정에는 공개 식별자만 담기고 서버 access token 은 노출되지 않는다."""
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "AIza-test-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "641162137323")
    html = logged_in.get("/connect").get_data(as_text=True)

    assert "ya29.server-session-token" not in html
    # 공개 설정값은 포함된다 (리퍼러 · API 제한 전제의 브라우저 키)
    assert "AIza-test-picker-key" in html


def test_nonjs_form_fallback_still_posts_to_connect(logged_in, monkeypatch):
    """JS 미사용 폼 폴백(POST /connect) 회귀 — URL 연결 경로."""
    _mock_attach_success(monkeypatch, title="폼 폴백 시트")
    resp = logged_in.post("/connect", data={
        "csrf_token": CSRF,
        "action": "connect",
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{VALID_SHEET_ID}/edit",
        "worksheet_name": "",
    })
    assert resp.status_code == 302
    with logged_in.session_transaction() as sess:
        assert sess["sheet_id"] == VALID_SHEET_ID


# ── 5. /connect/use-picked 검증 ───────────────────────────────────────────

def test_use_picked_requires_login(client):
    # CSRF 는 통과시키고 로그인만 없는 상태를 만든다.
    with client.session_transaction() as sess:
        sess["_csrf_token"] = CSRF
    resp = client.post("/connect/use-picked", json={"sheet_id": VALID_SHEET_ID},
                       headers={"X-CSRF-Token": CSRF})
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


def test_use_picked_rejects_missing_csrf(logged_in):
    resp = _json_post(logged_in, "/connect/use-picked",
                      {"sheet_id": VALID_SHEET_ID}, csrf=None)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


@pytest.mark.parametrize("bad_id", [
    "",                       # 빈 값
    "short",                  # 너무 짧음
    "has space in id 1234",   # 허용되지 않는 문자
    "id/with/slash0123456",   # 경로 문자
    "x" * 200,                # 과도한 길이
])
def test_use_picked_rejects_invalid_sheet_id(logged_in, bad_id):
    resp = _json_post(logged_in, "/connect/use-picked", {"sheet_id": bad_id})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_use_picked_rejects_overlong_worksheet_name(logged_in):
    resp = _json_post(logged_in, "/connect/use-picked", {
        "sheet_id": VALID_SHEET_ID,
        "worksheet_name": "w" * 101,
    })
    assert resp.status_code == 400


def test_use_picked_success_connects_sheet(logged_in, monkeypatch):
    _mock_attach_success(monkeypatch, title="실제 시트 제목")
    resp = _json_post(logged_in, "/connect/use-picked", {"sheet_id": VALID_SHEET_ID})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["sheet_id"] == VALID_SHEET_ID
    with logged_in.session_transaction() as sess:
        assert sess["sheet_id"] == VALID_SHEET_ID


# ── 6. 클라이언트 제목 불신 ───────────────────────────────────────────────

def test_use_picked_stores_server_title_not_client_title(logged_in, monkeypatch):
    _mock_attach_success(monkeypatch, title="서버가 조회한 제목")
    resp = _json_post(logged_in, "/connect/use-picked", {
        "sheet_id": VALID_SHEET_ID,
        "title": "<img onerror=x> 클라이언트 조작 제목",
    })
    data = resp.get_json()
    assert data["title"] == "서버가 조회한 제목"
    with logged_in.session_transaction() as sess:
        assert sess["sheet_title"] == "서버가 조회한 제목"


# ── 오류 정제 (403 / 404) ─────────────────────────────────────────────────

class _ApiError(Exception):
    def __init__(self, status):
        super().__init__("internal detail: user@example.com /secret/path token=abc")
        self.status_code = status


@pytest.mark.parametrize("status,expected", [
    (403, "시트 접근 권한이 없습니다."),
    (404, "시트를 찾을 수 없습니다."),
])
def test_use_picked_sanitizes_api_errors(logged_in, monkeypatch, status, expected):
    monkeypatch.setattr(sheet_module, "get_credentials", lambda: object())

    def _raise(credentials, sheet_id):
        raise _ApiError(status)

    monkeypatch.setattr(sheet_module, "verify_sheet_access", _raise)
    resp = _json_post(logged_in, "/connect/use-picked", {"sheet_id": VALID_SHEET_ID})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == expected
    # 예외 원문(내부 경로 · 이메일 · 토큰)이 응답에 없다
    body = resp.get_data(as_text=True)
    assert "internal detail" not in body
    assert "/secret/path" not in body


# ── 8. scope version 마이그레이션 ─────────────────────────────────────────

def test_save_device_session_records_current_scope_version(db):
    fs.save_device_session("device-1", USER_A, "refresh-1")
    doc = db.docs(fs.DEVICE_SESSIONS_COLLECTION)["device-1"]
    assert doc["scope_version"] == OAUTH_SCOPE_VERSION


def test_restore_context_reports_scope_version(db):
    fs.save_device_session("device-new", USER_A, "refresh-new")
    fs.save_device_session("device-old", USER_A, "refresh-old", scope_version=1)

    assert fs.restore_device_context("device-new")["scope_version"] == OAUTH_SCOPE_VERSION
    assert fs.restore_device_context("device-old")["scope_version"] == 1


def test_missing_scope_version_is_treated_as_outdated(db):
    """scope_version 미기록(전환 이전) 문서는 구버전으로 판별되어야 한다."""
    fs.save_device_session("device-legacy", USER_A, "refresh-legacy")
    db.docs(fs.DEVICE_SESSIONS_COLLECTION)["device-legacy"].pop("scope_version")
    assert fs.restore_device_context("device-legacy")["scope_version"] == 1


def test_outdated_scope_version_blocks_auto_restore(client, db, monkeypatch):
    """구버전 refresh token 은 자동 복원되지 않고 재동의 경로로 남는다."""
    fs.save_device_session("device-old", USER_A, "refresh-old", scope_version=1)
    with client.session_transaction() as sess:
        sess["device_id"] = "device-old"

    called = {"refresh": False}

    def _no_refresh(token, refresh_token):
        called["refresh"] = True
        raise AssertionError("구버전 토큰으로 갱신을 시도하면 안 된다")

    monkeypatch.setattr(app_module, "_build_credentials", _no_refresh)
    client.get("/settings")

    assert called["refresh"] is False
    with client.session_transaction() as sess:
        assert "credentials" not in sess
        # refresh token 문서는 파괴하지 않는다 (재동의 후 갱신)
    assert "device-old" in db.docs(fs.DEVICE_SESSIONS_COLLECTION)


def test_current_scope_version_allows_auto_restore(client, db, monkeypatch):
    fs.save_user_sheet(USER_A, "sheet-a", "A 시트", "작품목록")
    fs.save_device_session("device-new", USER_A, "refresh-new")
    with client.session_transaction() as sess:
        sess["device_id"] = "device-new"

    class _Creds:
        token = "restored-access-token"
        expiry = None
        refresh_token = "refresh-new"

        def refresh(self, request):
            return None

    monkeypatch.setattr(app_module, "_build_credentials",
                        lambda token, refresh_token: _Creds())
    client.get("/settings")

    with client.session_transaction() as sess:
        assert sess["credentials"]["token"] == "restored-access-token"
        assert sess["user_key"] == USER_A
        assert sess["sheet_id"] == "sheet-a"
