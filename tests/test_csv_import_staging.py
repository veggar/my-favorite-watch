"""services.csv_import_staging 단위 테스트 + 쿠키 비노출 회귀 테스트.

`csv_import_data`(파싱 결과 원본)를 서명된 __session 쿠키에 직접 담으면,
쿠키 값을 base64 디코드하는 것만으로 후기·줄거리 등 원문이 그대로 읽힌다
(PRD §16.1). 이 테스트는 (1) 저장소 자체의 저장/조회/1회성 소비를 검증하고,
(2) 실제 업로드 라우트를 거친 뒤 쿠키 안에 파싱 결과 원문이 없는지
직접 복호화해서 확인한다.
"""
import io

import pytest

from tests.fake_firestore import FakeFirestoreClient

import services.csv_import_staging as staging
from app import app

SAMPLE_ITEMS = [{"title": "제목1", "review": "아주 은밀한 개인 후기"}]


# ── 저장소 단위 테스트 (Firestore 폴백: 프로세스 메모리) ────────────────────

def test_save_and_load_roundtrip():
    staging_id = staging.save(SAMPLE_ITEMS)
    assert staging_id
    loaded = staging.load_and_clear(staging_id)
    assert loaded == SAMPLE_ITEMS


def test_load_is_single_use():
    staging_id = staging.save(SAMPLE_ITEMS)
    assert staging.load_and_clear(staging_id) == SAMPLE_ITEMS
    assert staging.load_and_clear(staging_id) is None


def test_load_unknown_id_returns_none():
    assert staging.load_and_clear("does-not-exist") is None


def test_load_empty_id_returns_none():
    assert staging.load_and_clear("") is None
    assert staging.load_and_clear(None) is None


def test_different_saves_get_different_ids():
    a = staging.save(SAMPLE_ITEMS)
    b = staging.save(SAMPLE_ITEMS)
    assert a != b


# ── Firestore 구성 시: 문서 키가 원본이 아니라 해시인지 ─────────────────────

def test_document_key_is_hashed_not_raw_staging_id(monkeypatch):
    db = FakeFirestoreClient()
    monkeypatch.setattr("services.firestore_session.get_db", lambda: db)

    staging_id = staging.save(SAMPLE_ITEMS)
    doc_ids = list(db.docs(staging.COLLECTION))
    assert doc_ids == [staging._hash(staging_id)]
    assert staging_id not in doc_ids

    assert staging.load_and_clear(staging_id) == SAMPLE_ITEMS
    # 1회성 소비 후 문서도 삭제된다.
    assert list(db.docs(staging.COLLECTION)) == []


# ── 라우트 통합: 쿠키에 파싱 원문이 남지 않는지 ─────────────────────────────

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client, sheet_id=None):
    with client.session_transaction() as sess:
        sess["credentials"] = {"token": "fake"}
        sess["user_key"] = "user-1"
        sess["_csrf_token"] = "csrf-test-token"
        from services.session_state import auth_timestamp
        sess["auth_at"] = auth_timestamp()
        if sheet_id:
            sess["sheet_id"] = sheet_id
            sess["worksheet_name"] = "My Favorite Watch"


def _decode_cookie(client) -> dict:
    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    assert cookie is not None
    serializer = app.session_interface.get_signing_serializer(app)
    return dict(serializer.loads(cookie.value))


def test_upload_csv_preview_cookie_has_no_raw_review_text(client, monkeypatch):
    _login(client)

    csv_bytes = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,액션,새 작품,A,2026.01.01,2026.01.02,아주 은밀한 개인 후기\n"
    ).encode("utf-8")

    resp = client.post("/upload-csv", data={
        "csrf_token": "csrf-test-token",
        "action": "preview",
        "csv_file": (io.BytesIO(csv_bytes), "sample.csv"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200

    session_data = _decode_cookie(client)
    assert "csv_import_data" not in session_data  # 옛 키가 되살아나지 않았는지
    assert "csv_staging_id" in session_data
    # 쿠키 전체 어디에도 원문 리뷰 텍스트가 평문으로 없어야 한다.
    assert "은밀한 개인 후기" not in str(session_data)


def test_upload_csv_import_consumes_staging_and_clears_cookie(client, monkeypatch):
    import routes.sheet as sheet_module

    _login(client, sheet_id="sheet-1")
    monkeypatch.setattr(sheet_module, "get_credentials", lambda: object())
    monkeypatch.setattr(sheet_module, "get_items_title_map", lambda *a, **k: {})
    monkeypatch.setattr(sheet_module, "append_items_batch", lambda *a, **k: ["new-id-1"])
    import services.google_sheets as gs
    monkeypatch.setattr(gs, "append_item", lambda *a, **k: None, raising=False)

    csv_bytes = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,액션,새 작품,A,2026.01.01,2026.01.02,좋음\n"
    ).encode("utf-8")

    preview_resp = client.post("/upload-csv", data={
        "csrf_token": "csrf-test-token",
        "action": "preview",
        "csv_file": (io.BytesIO(csv_bytes), "sample.csv"),
    }, content_type="multipart/form-data")
    assert preview_resp.status_code == 200

    session_before = _decode_cookie(client)
    staging_id = session_before["csv_staging_id"]
    assert staging.load_and_clear.__module__  # sanity: module importable

    import_resp = client.post("/upload-csv", data={
        "csrf_token": "csrf-test-token",
        "action": "import",
    })
    assert import_resp.status_code == 302  # 성공 시 목록으로 리디렉션

    session_after = _decode_cookie(client)
    assert "csv_staging_id" not in session_after
    # 같은 staging id를 다시 소비하려 하면 이미 지워져 있어야 한다(1회용).
    assert staging.load_and_clear(staging_id) is None
