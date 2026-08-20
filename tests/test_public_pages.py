"""로그인 없이 접근 가능한 공개 라우트 테스트 (P0-4, P2-1).

`/privacy`, `/terms`, `/manifest.webmanifest`, `/favicon.ico` 는 Google OAuth
앱 검증(P0-2) 심사 시 미인증 상태로 접근되므로 `login_required` 를 붙이지
않는다. 이 테스트는 인증 없이도 200 을 반환하는지, 운영 주체 정보가 채워지지
않았을 때 화면에 그 사실이 드러나는지를 확인한다.
"""

import pytest

import app as app_module


@pytest.fixture
def client(monkeypatch):
    # 운영 주체 정보를 매 테스트에서 명시적으로 제어한다 (기본은 비움).
    for key in ("SERVICE_OPERATOR", "PRIVACY_CONTACT_EMAIL", "SERVICE_URL", "POLICY_EFFECTIVE_DATE"):
        monkeypatch.delenv(key, raising=False)
    return app_module.app.test_client()


def test_privacy_accessible_without_login(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200


def test_terms_accessible_without_login(client):
    resp = client.get("/terms")
    assert resp.status_code == 200


def test_privacy_shows_placeholder_when_operator_info_missing(client):
    resp = client.get("/privacy")
    body = resp.get_data(as_text=True)
    assert "운영 주체 정보가 아직 설정되지 않았습니다" in body
    assert "[운영 주체 미설정]" in body


def test_privacy_hides_warning_when_operator_info_set(client, monkeypatch):
    monkeypatch.setenv("SERVICE_OPERATOR", "테스트 운영자")
    monkeypatch.setenv("PRIVACY_CONTACT_EMAIL", "privacy@example.com")
    monkeypatch.setenv("SERVICE_URL", "https://example.com")
    monkeypatch.setenv("POLICY_EFFECTIVE_DATE", "2026-09-01")

    resp = client.get("/privacy")
    body = resp.get_data(as_text=True)
    assert "운영 주체 정보가 아직 설정되지 않았습니다" not in body
    assert "테스트 운영자" in body
    assert "privacy@example.com" in body


def test_terms_links_to_privacy_and_vice_versa(client):
    terms_body = client.get("/terms").get_data(as_text=True)
    assert "/privacy" in terms_body

    privacy_body = client.get("/privacy").get_data(as_text=True)
    assert "/terms" in privacy_body


def test_manifest_returns_valid_webmanifest(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"
    data = resp.get_json()
    assert data["name"] == "My Favorite Watch"
    assert data["start_url"] == "/"
    assert len(data["icons"]) == 3


def test_favicon_served(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200


def test_login_page_links_to_privacy_and_terms(client):
    resp = client.get("/login")
    body = resp.get_data(as_text=True)
    assert "/privacy" in body
    assert "/terms" in body
