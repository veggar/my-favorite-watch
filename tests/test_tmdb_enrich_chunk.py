"""P0-3 회귀 테스트 — 청크 동기 보강.

배포 환경(Cloud Run)에서 응답 반환 후 CPU 가 스로틀링되면 데몬 스레드가
중단되어 보강 결과가 조용히 유실됐다(계획서 P0-3 원인 2). 보강을 요청
수명 안에서 동기 처리하도록 바꾼 뒤의 동작을 검증한다.

실행: pytest -q
"""
import os

import pytest

os.environ.setdefault("TMDB_API_KEY", "test-key")

import services.tmdb as tmdb  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_tmdb(monkeypatch):
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "test-key")


def _item(item_id, title):
    return {"id": item_id, "title": title, "category": "영화",
            "titleLink": "", "officialRating": "", "originalTitle": "",
            "watched": "false"}


def test_chunk_enriches_and_writes_to_sheet(monkeypatch):
    monkeypatch.setattr(tmdb, "fetch_title_info", lambda title, category="": {
        "titleLink": f"https://www.themoviedb.org/movie/{title}",
        "officialRating": "8.1",
        "originalTitle": title.upper(),
    })
    written = []
    monkeypatch.setattr("services.google_sheets.update_item",
                        lambda *a, **k: written.append(a[2]))

    items = [_item("a", "alpha"), _item("b", "beta")]
    statuses = tmdb.enrich_items_chunk(None, "sheet", "ws", items, rate_limit_sec=0)

    assert statuses == {"a": "done", "b": "done"}
    assert written == ["a", "b"]
    assert items[0]["officialRating"] == "8.1"


def test_chunk_marks_not_found_when_tmdb_has_no_result(monkeypatch):
    monkeypatch.setattr(tmdb, "fetch_title_info", lambda title, category="": {
        "titleLink": "", "officialRating": "", "originalTitle": ""})
    monkeypatch.setattr("services.google_sheets.update_item", lambda *a, **k: None)

    statuses = tmdb.enrich_items_chunk(None, "sheet", "ws", [_item("a", "alpha")],
                                       rate_limit_sec=0)
    assert statuses == {"a": "not_found"}


def test_chunk_isolates_per_item_failure(monkeypatch):
    """한 항목이 실패해도 나머지 항목 처리는 계속되어야 한다."""
    monkeypatch.setattr(tmdb, "fetch_title_info", lambda title, category="": {
        "titleLink": f"https://x/{title}", "officialRating": "7.0",
        "originalTitle": title})

    def _update(creds, sheet_id, item_id, data, worksheet_name):
        if item_id == "a":
            raise RuntimeError("sheet write failed")

    monkeypatch.setattr("services.google_sheets.update_item", _update)

    statuses = tmdb.enrich_items_chunk(
        None, "sheet", "ws", [_item("a", "alpha"), _item("b", "beta")],
        rate_limit_sec=0)

    assert statuses["a"] == "not_found"
    assert statuses["b"] == "done"


def test_chunk_without_tmdb_key_clears_status(monkeypatch):
    monkeypatch.setattr(tmdb, "TMDB_API_KEY", "")
    statuses = tmdb.enrich_items_chunk(None, "sheet", "ws", [_item("a", "alpha")],
                                       rate_limit_sec=0)
    # 대기(⏳) 아이콘이 영원히 남지 않도록 빈 상태로 정리한다
    assert statuses == {"a": ""}


def test_chunk_size_is_bounded():
    """요청 수명 안에 끝나도록 청크 크기에 상한이 있어야 한다."""
    assert 1 <= tmdb.ENRICH_CHUNK_SIZE <= 50


def test_background_thread_entrypoint_is_removed():
    """데몬 스레드 기반 보강은 유실 위험이 있으므로 제거되어야 한다."""
    assert not hasattr(tmdb, "enrich_items_background")
