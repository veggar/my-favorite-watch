"""완전한 서버 측 세션 (task-2026-08-003) 검증.

재현 시나리오 (구현 전 실패해야 하는 테스트)
    Flask 세션 쿠키는 서명만 되고 암호화되지 않는다. 기존 구조에서는
    `credentials`(access token) · `user_key` · `user`(이름·이메일·프로필)가
    쿠키에 직접 담겨, 쿠키 값을 얻으면 base64 디코드만으로 전부 읽혔다.

    → `test_cookie_contains_no_server_side_keys` 가 이 문제의 재현이자
      수정 후 회귀 방지 테스트다. 문자열 포함 검사가 아니라 **같은 서명
      키로 쿠키를 직접 복호화**해서 키 목록을 확인한다(base64/압축 때문에
      리터럴 검사는 신뢰할 수 없다 — task-003 §5).

검증 항목 (task-003 §5)
    - server_session 단위: 저장/조회/삭제/만료/전체 삭제, 전체 치환 semantics
    - session_id 원본이 아니라 sha256 해시가 문서 키로 쓰이는지
    - Firestore 구성 시: 쿠키에 SERVER_SIDE_KEYS 부재, device_id 는 쿠키 유지
    - Firestore 미구성 시: 예전처럼 쿠키에 직접 담기는 폴백
    - 개별 로그아웃: 해당 server_sessions 문서만 삭제
    - 전체 로그아웃: 같은 user_key 의 모든 문서 삭제
    - 문서 소멸 시: 쿠키에 session_id 가 남아 있어도 재인증 요구
"""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.fake_firestore import FakeFirestoreClient

import services.server_session as server_session
from services.hybrid_session import SERVER_SIDE_KEYS, SESSION_ID_KEY
from app import app

COLLECTION = server_session.SESSIONS_COLLECTION

SAMPLE_PAYLOAD = {
    "credentials": {"token": "ya29.test-access-token", "expiry": "2026-08-20T00:00:00"},
    "user_key": "u" * 64,
    "user": {"name": "홍길동", "email": "test@example.com", "picture": ""},
    "sheet_id": "sheet-123",
    "sheet_title": "내 시트",
    "worksheet_name": "Sheet1",
    "auth_at": "2026-08-20T00:00:00+00:00",
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


def _decode_cookie(client) -> dict:
    """테스트 클라이언트에 저장된 세션 쿠키를 서명 키로 직접 복호화한다."""
    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    assert cookie is not None, "세션 쿠키가 없다"
    serializer = app.session_interface.get_signing_serializer(app)
    return dict(serializer.loads(cookie.value))


def _login(client, payload=None):
    with client.session_transaction() as sess:
        sess["device_id"] = "device-abc"
        sess["_csrf_token"] = "csrf-test-token"
        sess.permanent = True
        for key, value in (payload or SAMPLE_PAYLOAD).items():
            sess[key] = value


# ── server_session 단위 테스트 ─────────────────────────────────────────────

def test_new_session_id_is_random_and_long():
    a, b = server_session.new_session_id(), server_session.new_session_id()
    assert a != b
    assert len(a) >= 40


def test_document_key_is_sha256_not_raw_session_id(fake_db):
    sid = server_session.new_session_id()
    assert server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    doc_ids = list(fake_db.docs(COLLECTION))
    assert doc_ids == [hashlib.sha256(sid.encode()).hexdigest()]
    assert sid not in doc_ids


def test_save_get_roundtrip(fake_db):
    sid = server_session.new_session_id()
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    data = server_session.get_session(sid)
    assert data is not None
    for key, value in SAMPLE_PAYLOAD.items():
        assert data[key] == value


def test_save_is_full_replace_not_merge(fake_db):
    """credentials 를 pop 한 뒤 저장하면 문서에서도 사라져야 한다."""
    sid = server_session.new_session_id()
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    reduced = {k: v for k, v in SAMPLE_PAYLOAD.items() if k != "credentials"}
    server_session.save_session(sid, reduced)
    data = server_session.get_session(sid)
    assert "credentials" not in data
    assert data["user_key"] == SAMPLE_PAYLOAD["user_key"]


def test_save_preserves_created_at(fake_db):
    sid = server_session.new_session_id()
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    doc = next(iter(fake_db.docs(COLLECTION).values()))
    created = doc["created_at"]
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    doc = next(iter(fake_db.docs(COLLECTION).values()))
    assert doc["created_at"] == created


def test_expired_session_returns_none_and_is_deleted(fake_db):
    sid = server_session.new_session_id()
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    doc_id = next(iter(fake_db.docs(COLLECTION)))
    fake_db.docs(COLLECTION)[doc_id]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(days=1)
    )
    assert server_session.get_session(sid) is None
    assert doc_id not in fake_db.docs(COLLECTION)


def test_delete_session(fake_db):
    sid = server_session.new_session_id()
    server_session.save_session(sid, dict(SAMPLE_PAYLOAD))
    server_session.delete_session(sid)
    assert server_session.get_session(sid) is None
    assert fake_db.docs(COLLECTION) == {}


def test_delete_all_sessions_for_user(fake_db):
    for _ in range(2):
        server_session.save_session(
            server_session.new_session_id(), dict(SAMPLE_PAYLOAD)
        )
    other = dict(SAMPLE_PAYLOAD, user_key="x" * 64)
    other_sid = server_session.new_session_id()
    server_session.save_session(other_sid, other)

    removed = server_session.delete_all_sessions_for_user(SAMPLE_PAYLOAD["user_key"])
    assert removed == 2
    assert len(fake_db.docs(COLLECTION)) == 1
    assert server_session.get_session(other_sid) is not None


def test_unconfigured_is_safe(monkeypatch):
    monkeypatch.setattr(server_session, "_db", None)
    assert server_session.is_configured() is False
    assert server_session.save_session("sid", {}) is False
    assert server_session.get_session("sid") is None
    assert server_session.delete_all_sessions_for_user("u") == 0


# ── HybridSessionInterface: 쿠키 분리 ─────────────────────────────────────

def test_cookie_contains_no_server_side_keys(client, fake_db):
    """핵심 재현/회귀 테스트 — 쿠키를 복호화해 키 목록을 직접 확인한다."""
    _login(client)
    cookie_data = _decode_cookie(client)

    leaked = SERVER_SIDE_KEYS & set(cookie_data)
    assert not leaked, f"민감 키가 쿠키에 남아 있다: {leaked}"
    # 비민감 값과 session_id 는 쿠키에 남는다 (task-003 §2)
    assert cookie_data.get("device_id") == "device-abc"
    assert cookie_data.get("_csrf_token") == "csrf-test-token"
    assert cookie_data.get(SESSION_ID_KEY)


def test_server_document_holds_the_values(client, fake_db):
    _login(client)
    docs = fake_db.docs(COLLECTION)
    assert len(docs) == 1
    doc = next(iter(docs.values()))
    assert doc["credentials"]["token"] == "ya29.test-access-token"
    assert doc["user_key"] == SAMPLE_PAYLOAD["user_key"]


def test_session_roundtrip_after_split(client, fake_db):
    """다음 요청에서 서버 측 값이 세션으로 다시 병합되는지."""
    _login(client)
    with client.session_transaction() as sess:
        assert sess.get("credentials", {}).get("token") == "ya29.test-access-token"
        assert sess.get("sheet_id") == "sheet-123"
        assert sess.get("device_id") == "device-abc"


def test_popped_key_disappears_from_server_document(client, fake_db):
    """인증 신선도 만료로 credentials 를 pop 하면 문서에서도 사라져야 한다."""
    _login(client)
    with client.session_transaction() as sess:
        sess.pop("credentials", None)
        sess.pop("user", None)
    doc = next(iter(fake_db.docs(COLLECTION).values()))
    assert "credentials" not in doc
    assert doc["sheet_id"] == "sheet-123"


def test_fallback_without_firestore(monkeypatch):
    """Firestore 미구성 시 예전처럼 쿠키에 직접 담긴다 (로컬 개발 폴백)."""
    monkeypatch.setattr(server_session, "_db", None)
    app.config["TESTING"] = True
    with app.test_client() as c:
        _login(c)
        cookie_data = _decode_cookie(c)
        assert cookie_data.get("credentials", {}).get("token") == "ya29.test-access-token"
        assert SESSION_ID_KEY not in cookie_data


def test_legacy_cookie_migrates_on_next_write(fake_db, monkeypatch):
    """구 쿠키(값이 최상위에 직접 존재)가 다음 쓰기에서 신규 구조로 넘어간다."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        # 1) 미구성 폴백 상태에서 로그인 → 구 형식 쿠키 생성
        monkeypatch.setattr(server_session, "_db", None)
        _login(c)
        assert SESSION_ID_KEY not in _decode_cookie(c)
        # 2) Firestore 가 구성된 뒤 세션이 변경되는 요청
        monkeypatch.setattr(server_session, "_db", fake_db)
        with c.session_transaction() as sess:
            assert sess.get("user_key") == SAMPLE_PAYLOAD["user_key"]  # 구 쿠키 읽힘
            sess["auth_at"] = "2026-08-20T01:00:00+00:00"
        cookie_data = _decode_cookie(c)
        assert not (SERVER_SIDE_KEYS & set(cookie_data))
        assert cookie_data.get(SESSION_ID_KEY)
        assert len(fake_db.docs(COLLECTION)) == 1


# ── 로그아웃 ──────────────────────────────────────────────────────────────

def test_logout_deletes_only_this_session(client, fake_db):
    _login(client)
    # 다른 기기의 세션 문서
    other_sid = server_session.new_session_id()
    server_session.save_session(other_sid, dict(SAMPLE_PAYLOAD))
    assert len(fake_db.docs(COLLECTION)) == 2

    resp = client.post("/logout", data={"csrf_token": "csrf-test-token"})
    assert resp.status_code == 302
    assert len(fake_db.docs(COLLECTION)) == 1
    assert server_session.get_session(other_sid) is not None


def test_logout_all_deletes_every_session_of_user(client, fake_db):
    _login(client)
    server_session.save_session(
        server_session.new_session_id(), dict(SAMPLE_PAYLOAD)
    )
    other = dict(SAMPLE_PAYLOAD, user_key="x" * 64)
    other_sid = server_session.new_session_id()
    server_session.save_session(other_sid, other)

    resp = client.post("/logout-all", data={"csrf_token": "csrf-test-token"})
    assert resp.status_code == 302
    remaining = fake_db.docs(COLLECTION)
    assert len(remaining) == 1
    assert next(iter(remaining.values()))["user_key"] == "x" * 64


def test_missing_server_document_requires_reauth(client, fake_db):
    """문서가 사라지면(만료·전체 로그아웃) 쿠키의 session_id 만으로는
    로그인 필요 라우트에 접근할 수 없어야 한다."""
    _login(client)
    fake_db.docs(COLLECTION).clear()
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
