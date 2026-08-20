"""가져오기 영향 범위 미리 계산 라우트 테스트 (P2-4).

`/import-sheet` 의 analyze 단계와 `/upload-csv` 의 preview 단계가 실제로
`services.import_plan.plan_import` 를 호출해 화면에 추가·중복 건수를
보여주는지 확인한다. Google Sheets API 는 호출하지 않도록 `routes.sheet`
모듈에 임포트된 이름을 직접 monkeypatch 한다.
"""

import io

import pytest

import app as app_module
import routes.sheet as sheet_module
from services.session_state import auth_timestamp

CSRF = "csrf-test-token"


@pytest.fixture
def client():
    return app_module.app.test_client()


def _login(client, sheet_id="sheet-1", worksheet_name="My Favorite Watch"):
    with client.session_transaction() as sess:
        sess["credentials"] = {"token": "fake"}
        sess["user_key"] = "user-1"
        sess["_csrf_token"] = CSRF
        # expire_stale_credentials(app.py) 가 auth_at 없는 세션의 credentials 를
        # 제거하므로, 로그인 상태를 유지하려면 신선한 타임스탬프가 필요하다.
        sess["auth_at"] = auth_timestamp()
        if sheet_id:
            sess["sheet_id"] = sheet_id
            sess["sheet_title"] = "내 시트"
            sess["worksheet_name"] = worksheet_name


def test_import_sheet_analyze_computes_plan(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(sheet_module, "get_credentials", lambda: object())
    monkeypatch.setattr(
        sheet_module, "verify_sheet_access",
        lambda creds, sheet_id: {"title": "소스 시트", "worksheets": ["Sheet1"]},
    )
    monkeypatch.setattr(
        sheet_module, "read_source_items",
        lambda creds, sheet_id, worksheet: [{"title": "New Item"}, {"title": "Existing Item"}],
    )
    monkeypatch.setattr(
        sheet_module, "_existing_title_map_or_none",
        lambda creds, sheet_id, worksheet: {"existing item": {"title": "Existing Item"}},
    )

    resp = client.post("/import-sheet", data={
        "csrf_token": CSRF,
        "action": "analyze",
        "src_sheet_id": "src-sheet-1",
        "src_worksheet": "Sheet1",
    })

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "추가 (건)" in body
    assert "1건" in body or ">1<" in body  # to_add == 1


def test_import_sheet_analyze_handles_unreadable_destination(client, monkeypatch):
    """대상 시트 조회가 실패해도 가져오기 자체는 막지 않는다."""
    _login(client)
    monkeypatch.setattr(sheet_module, "get_credentials", lambda: object())
    monkeypatch.setattr(
        sheet_module, "verify_sheet_access",
        lambda creds, sheet_id: {"title": "소스 시트", "worksheets": ["Sheet1"]},
    )
    monkeypatch.setattr(
        sheet_module, "read_source_items",
        lambda creds, sheet_id, worksheet: [{"title": "A"}],
    )

    def _boom(creds, sheet_id, worksheet):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(sheet_module, "get_items_title_map", _boom)

    resp = client.post("/import-sheet", data={
        "csrf_token": CSRF,
        "action": "analyze",
        "src_sheet_id": "src-sheet-1",
        "src_worksheet": "Sheet1",
    })

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 확인 불가 안내가 나오지만 가져오기 버튼(추가 건수)은 그대로 노출된다.
    assert "현재 연결된 시트를 읽지 못해" in body


def test_upload_csv_preview_computes_plan_when_sheet_connected(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(sheet_module, "get_credentials", lambda: object())
    monkeypatch.setattr(
        sheet_module, "_existing_title_map_or_none",
        lambda creds, sheet_id, worksheet: {},
    )

    csv_bytes = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,액션,새 작품,A,2026.01.01,2026.01.02,좋음\n"
    ).encode("utf-8")

    resp = client.post("/upload-csv", data={
        "csrf_token": CSRF,
        "action": "preview",
        "csv_file": (io.BytesIO(csv_bytes), "sample.csv"),
    }, content_type="multipart/form-data")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "추가 (건)" in body


def test_upload_csv_preview_skips_plan_when_no_sheet_connected(client, monkeypatch):
    _login(client, sheet_id=None)

    csv_bytes = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,액션,새 작품,A,2026.01.01,2026.01.02,좋음\n"
    ).encode("utf-8")

    resp = client.post("/upload-csv", data={
        "csrf_token": CSRF,
        "action": "preview",
        "csv_file": (io.BytesIO(csv_bytes), "sample.csv"),
    }, content_type="multipart/form-data")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 시트가 연결되지 않았으므로 plan 계산 없이 기존 요약만 보여준다.
    assert "추가 (건)" not in body
