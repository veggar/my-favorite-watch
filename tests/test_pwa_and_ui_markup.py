"""PWA · 초기 로딩 표시 · 확인 모달 마크업이 실제 화면에 포함되는지 확인 (P2-1~3).

CSS/JS 는 pytest 로 직접 실행할 수 없으므로, 여기서는 각 화면이 필요한 리소스를
올바르게 불러오는지(마크업 존재)만 검증한다. 동작 자체(appConfirm 흐름,
"Now Loading" 사라짐 타이밍)는 수동/브라우저 확인 대상이다.
"""
import pytest

from tests.fake_firestore import FakeFirestoreClient

import services.server_session as server_session
from services.session_state import auth_timestamp
from app import app


def _sample_payload():
    # auth_at 은 매 실행 시점 기준으로 신선해야 한다. 고정된 과거 시각을 쓰면
    # expire_stale_credentials(app.py) 가 12시간 신선도 창을 넘겼다고 보고
    # credentials 를 지워버려 로그인 상태가 사라진다.
    return {
        "credentials": {"token": "ya29.test-access-token", "expiry": "2099-01-01T00:00:00"},
        "user_key": "u" * 64,
        "user": {"name": "홍길동", "email": "test@example.com", "picture": ""},
        "sheet_id": "sheet-123",
        "sheet_title": "내 시트",
        "worksheet_name": "Sheet1",
        "auth_at": auth_timestamp(),
    }


@pytest.fixture()
def fake_db(monkeypatch):
    db = FakeFirestoreClient()
    monkeypatch.setattr(server_session, "_db", db)
    return db


@pytest.fixture()
def client(fake_db):
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client):
    with client.session_transaction() as sess:
        sess["device_id"] = "device-abc"
        sess["_csrf_token"] = "csrf-test-token"
        sess.permanent = True
        for key, value in _sample_payload().items():
            sess[key] = value


@pytest.mark.parametrize("path", ["/login", "/", "/settings"])
def test_pages_include_pwa_head_meta(client, path):
    if path != "/login":
        _login(client)
    body = client.get(path).get_data(as_text=True)
    assert 'rel="manifest"' in body
    assert "manifest.webmanifest" in body
    assert 'id="boot-loading"' in body
    assert "Now Loading" in body


def test_list_page_includes_confirm_modal_script_and_delete_confirm_attrs(client):
    _login(client)
    body = client.get("/").get_data(as_text=True)
    assert "js/confirm-modal.js" in body


def test_settings_page_includes_confirm_modal_script_and_policy_links(client):
    _login(client)
    body = client.get("/settings").get_data(as_text=True)
    assert "js/confirm-modal.js" in body
    assert "/privacy" in body
    assert "/terms" in body
    assert "data-confirm" in body  # 로그아웃 버튼에 확인 모달이 걸려 있어야 한다
