"""services.site_info.policy_context 단위 테스트 (P0-4).

운영자명 · 연락처는 개인정보이므로 하드코딩하지 않고 환경 변수로 주입한다.
값이 비어 있으면 화면에서 알아챌 수 있도록 placeholder 와 missing 목록을
정확히 돌려주는지 확인한다.
"""

import pytest

from services.site_info import REQUIRED_KEYS, policy_context


@pytest.fixture(autouse=True)
def _clear_policy_env(monkeypatch):
    for key in ("SERVICE_OPERATOR", "PRIVACY_CONTACT_EMAIL", "SERVICE_URL", "POLICY_EFFECTIVE_DATE"):
        monkeypatch.delenv(key, raising=False)


def test_all_missing_by_default():
    ctx = policy_context()
    assert ctx["is_complete"] is False
    assert {m["key"] for m in ctx["missing"]} == set(REQUIRED_KEYS)
    assert ctx["operator"] == "[운영 주체 미설정]"


def test_complete_when_all_env_vars_set(monkeypatch):
    monkeypatch.setenv("SERVICE_OPERATOR", "운영자")
    monkeypatch.setenv("PRIVACY_CONTACT_EMAIL", "a@b.com")
    monkeypatch.setenv("SERVICE_URL", "https://example.com")
    monkeypatch.setenv("POLICY_EFFECTIVE_DATE", "2026-09-01")

    ctx = policy_context()
    assert ctx["is_complete"] is True
    assert ctx["missing"] == []
    assert ctx["operator"] == "운영자"
    assert ctx["service_url"] == "https://example.com"


def test_blank_string_env_var_counts_as_missing(monkeypatch):
    monkeypatch.setenv("SERVICE_OPERATOR", "   ")
    ctx = policy_context()
    assert any(m["key"] == "operator" for m in ctx["missing"])
    assert ctx["operator"] == "[운영 주체 미설정]"


def test_partial_completion_lists_only_missing_keys(monkeypatch):
    monkeypatch.setenv("SERVICE_OPERATOR", "운영자")
    monkeypatch.setenv("SERVICE_URL", "https://example.com")

    ctx = policy_context()
    assert ctx["is_complete"] is False
    missing_keys = {m["key"] for m in ctx["missing"]}
    assert missing_keys == {"contact_email", "effective_date"}
