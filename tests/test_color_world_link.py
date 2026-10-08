"""컬러로 세계여행 테스트 참여 링크 생성 테스트 (TASK-2026-008 CR-03).

링크는 승인된 독립 서비스 origin 의 `/collect.html` 에 `campaign` query 하나만
붙인다. campaign ID 가 없거나 형식이 맞지 않으면 `None` 을 돌려 로그인 화면에서
버튼을 숨긴다(fail-closed).
"""

from urllib.parse import parse_qs, urlsplit

import pytest

from services.color_world_link import (
    CAMPAIGN_ENV,
    PLAYTEST_COLLECT_URL,
    app_playtest_url_from_env,
    build_app_playtest_url,
)


def test_valid_app_campaign_builds_exact_url():
    url = build_app_playtest_url("f1-formal-1-app")
    assert url == f"{PLAYTEST_COLLECT_URL}?campaign=f1-formal-1-app"


def test_url_has_only_campaign_query_and_approved_origin():
    parts = urlsplit(build_app_playtest_url("f1-formal-1-app"))
    assert parts.scheme == "https"
    assert parts.netloc == "ccatlas-f1-459669244480.asia-northeast3.run.app"
    assert parts.path == "/collect.html"
    assert parse_qs(parts.query) == {"campaign": ["f1-formal-1-app"]}
    assert parts.fragment == ""


def test_surrounding_whitespace_is_trimmed():
    assert build_app_playtest_url("  f1-formal-1-app\n") == (
        f"{PLAYTEST_COLLECT_URL}?campaign=f1-formal-1-app"
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "f1-formal-1-blog",  # 다른 채널
        "f1-formal-1-sns",
        "f1-formal-1-web",
        "F1-formal-1-app",  # 대문자
        "1f-formal-1-app",  # 숫자로 시작
        "f1 formal-1-app",  # 공백
        "f1-formal-1-app&utm_source=x",
        "f1-formal-1-app?x=1",
        "f1-formal-1-app#top",
        "https://example.com/?campaign=f1-formal-1-app",
        "-app",  # 길이 미달
        "a" + "b" * 37 + "-app",  # 42자, 패턴 상한(41자) 초과
        "f1-formal-1-app,OTHER=1",  # --set-env-vars 구분자
    ],
)
def test_invalid_or_other_channel_campaign_returns_none(value):
    assert build_app_playtest_url(value) is None


def test_max_length_app_campaign_is_accepted():
    value = "a" + "b" * 36 + "-app"  # 41자
    assert build_app_playtest_url(value) == f"{PLAYTEST_COLLECT_URL}?campaign={value}"


def test_from_env_reads_campaign(monkeypatch):
    monkeypatch.setenv(CAMPAIGN_ENV, "f1-formal-1-app")
    assert app_playtest_url_from_env() == f"{PLAYTEST_COLLECT_URL}?campaign=f1-formal-1-app"


def test_from_env_missing_returns_none(monkeypatch):
    monkeypatch.delenv(CAMPAIGN_ENV, raising=False)
    assert app_playtest_url_from_env() is None
