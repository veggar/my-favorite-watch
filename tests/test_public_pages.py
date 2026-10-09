"""로그인 없이 접근 가능한 공개 라우트 테스트 (P0-4, P2-1).

`/privacy`, `/terms`, `/manifest.webmanifest`, `/favicon.ico` 는 Google OAuth
앱 검증(P0-2) 심사 시 미인증 상태로 접근되므로 `login_required` 를 붙이지
않는다. 이 테스트는 인증 없이도 200 을 반환하는지, 운영 주체 정보가 채워지지
않았을 때 화면에 그 사실이 드러나는지를 확인한다.
"""

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pytest

import app as app_module


@pytest.fixture
def client(monkeypatch):
    # 운영 주체 정보를 매 테스트에서 명시적으로 제어한다 (기본은 비움).
    for key in (
        "SERVICE_OPERATOR",
        "PRIVACY_CONTACT_EMAIL",
        "SERVICE_URL",
        "POLICY_EFFECTIVE_DATE",
        "COLOR_WORLD_APP_CAMPAIGN_ID",
    ):
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


# ===== 로그인 화면 외부 테스트 참여 링크 (TASK-2026-008 CR-03) =====

PLAYTEST_HOST = "ccatlas-f1-459669244480.asia-northeast3.run.app"


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchors.append(dict(attrs))


def _login_anchors(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    parser = _AnchorCollector()
    parser.feed(resp.get_data(as_text=True))
    return parser.anchors


def _playtest_anchors(anchors):
    return [a for a in anchors if urlsplit(a.get("href", "")).netloc == PLAYTEST_HOST]


def test_login_hides_playtest_link_when_campaign_unset(client):
    anchors = _login_anchors(client)
    assert _playtest_anchors(anchors) == []
    body = client.get("/login").get_data(as_text=True)
    assert "external-test" not in body


@pytest.mark.parametrize("value", ["", "f1-formal-1-blog", "f1-formal-1-app&x=1"])
def test_login_hides_playtest_link_when_campaign_invalid(client, monkeypatch, value):
    monkeypatch.setenv("COLOR_WORLD_APP_CAMPAIGN_ID", value)
    assert _playtest_anchors(_login_anchors(client)) == []


def test_login_shows_single_playtest_link_when_campaign_set(client, monkeypatch):
    monkeypatch.setenv("COLOR_WORLD_APP_CAMPAIGN_ID", "f1-formal-1-app")
    anchors = _login_anchors(client)
    links = _playtest_anchors(anchors)
    assert len(links) == 1
    link = links[0]

    parts = urlsplit(link["href"])
    assert parts.scheme == "https"
    assert parts.path == "/collect.html"
    assert parse_qs(parts.query) == {"campaign": ["f1-formal-1-app"]}
    assert link["target"] == "_blank"
    assert set(link["rel"].split()) == {"noopener", "noreferrer"}
    assert link["aria-label"] == "컬러로 세계여행 테스트 참여 (새 창에서 열림)"

    body = client.get("/login").get_data(as_text=True)
    assert "새 퍼즐 게임 테스트" in body
    assert "컬러로 세계여행 테스트 참여</a>" in body
    assert "10분 내외 · 익명 참여 · 새 게임 서비스로 이동" in body
    assert "25분" not in body


def test_login_existing_links_unchanged_with_playtest_link(client, monkeypatch):
    hrefs_without = [a.get("href") for a in _login_anchors(client)]
    monkeypatch.setenv("COLOR_WORLD_APP_CAMPAIGN_ID", "f1-formal-1-app")
    anchors = _login_anchors(client)
    hrefs_with = [a.get("href") for a in anchors if a not in _playtest_anchors(anchors)]
    assert hrefs_with == hrefs_without
    assert "/auth/google" in hrefs_with
