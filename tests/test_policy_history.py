"""services.policy_history 단위 테스트 + /privacy/history, /terms/history 라우트 테스트.

PRD §5.1: "개인정보처리방침 변경 시 시행일과 이전 버전을 함께 제공한다."
스냅샷 저장/조회 로직과, 경로 파라미터(`slug`)를 통한 디렉터리 탈출 시도가
막히는지를 확인한다.
"""
import pytest

import services.policy_history as ph
import app as app_module


@pytest.fixture(autouse=True)
def _isolated_history_root(tmp_path, monkeypatch):
    """실제 docs/legal/history/ 를 건드리지 않도록 임시 디렉터리로 바꾼다."""
    monkeypatch.setattr(ph, "HISTORY_ROOT", tmp_path / "history")


@pytest.fixture
def client():
    return app_module.app.test_client()


# ── is_safe_slug ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug", ["2026-08-20", "2026-08-20_v2", "2026.08.20"])
def test_safe_slugs_accepted(slug):
    assert ph.is_safe_slug(slug)


@pytest.mark.parametrize("slug", ["", "..", "../etc", "a/b", "a\\b", "a b", None])
def test_unsafe_slugs_rejected(slug):
    assert not ph.is_safe_slug(slug)


# ── write_version / read_version / list_versions ────────────────────────────

def test_write_then_read_roundtrip():
    ph.write_version("privacy", "2026-08-20", "<html>v1</html>")
    assert ph.read_version("privacy", "2026-08-20") == "<html>v1</html>"


def test_write_duplicate_slug_raises():
    ph.write_version("privacy", "2026-08-20", "<html>v1</html>")
    with pytest.raises(FileExistsError):
        ph.write_version("privacy", "2026-08-20", "<html>overwrite attempt</html>")
    # 원본이 훼손되지 않아야 한다.
    assert ph.read_version("privacy", "2026-08-20") == "<html>v1</html>"


def test_write_unknown_doc_type_raises():
    with pytest.raises(ValueError):
        ph.write_version("not-a-real-type", "2026-08-20", "<html></html>")


def test_write_unsafe_slug_raises():
    with pytest.raises(ValueError):
        ph.write_version("privacy", "../../etc/passwd", "<html></html>")


def test_read_missing_version_returns_none():
    assert ph.read_version("privacy", "2099-01-01") is None


def test_read_unsafe_slug_returns_none_not_raise():
    assert ph.read_version("privacy", "../../../etc/passwd") is None


def test_list_versions_sorted_newest_first():
    ph.write_version("privacy", "2026-01-01", "<html>old</html>")
    ph.write_version("privacy", "2026-08-20", "<html>new</html>")
    assert ph.list_versions("privacy") == ["2026-08-20", "2026-01-01"]


def test_list_versions_empty_when_none_saved():
    assert ph.list_versions("privacy") == []


def test_list_versions_unknown_doc_type_returns_empty():
    assert ph.list_versions("nope") == []


def test_privacy_and_terms_history_are_independent():
    ph.write_version("privacy", "2026-08-20", "<html>privacy</html>")
    assert ph.list_versions("terms") == []
    assert ph.read_version("terms", "2026-08-20") is None


# ── 라우트: /privacy/history, /terms/history ────────────────────────────────

def test_history_list_route_empty_state(client):
    resp = client.get("/privacy/history")
    assert resp.status_code == 200
    assert "아직 보관된 이전 버전이 없습니다" in resp.get_data(as_text=True)


def test_history_list_route_shows_saved_versions(client):
    ph.write_version("privacy", "2026-01-01", "<html>old</html>")
    resp = client.get("/privacy/history")
    body = resp.get_data(as_text=True)
    assert "2026-01-01" in body


def test_history_view_route_serves_snapshot_verbatim(client):
    ph.write_version("terms", "2026-01-01", "<html><body>frozen content</body></html>")
    resp = client.get("/terms/history/2026-01-01")
    assert resp.status_code == 200
    assert "frozen content" in resp.get_data(as_text=True)


def test_history_view_route_404_for_missing_slug(client):
    resp = client.get("/privacy/history/2099-01-01")
    assert resp.status_code == 404


@pytest.mark.parametrize("slug", ["..", "%2e%2e", ".."])
def test_history_view_route_blocks_traversal(client, slug):
    resp = client.get(f"/privacy/history/{slug}")
    assert resp.status_code == 404


def test_privacy_page_shows_history_link_only_when_versions_exist(client):
    body_before = client.get("/privacy").get_data(as_text=True)
    assert "/privacy/history" not in body_before

    ph.write_version("privacy", "2026-01-01", "<html>old</html>")

    body_after = client.get("/privacy").get_data(as_text=True)
    assert "/privacy/history" in body_after
