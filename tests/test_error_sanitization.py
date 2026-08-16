"""P0-6 회귀 테스트 — 예외 원문 노출 차단.

Google API 오류 본문에는 내부 식별자 · 요청 정보가 포함될 수 있으므로
예외 문자열이 화면에 그대로 렌더링되면 안 된다.
(`.claude/rules/security.md` "Sanitization")

실행: pytest -q
"""
import pathlib
import re

import pytest

from services.errors import GENERIC_MESSAGE, friendly_error, http_status

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 실제 Google API 오류 본문과 유사한 문자열 (내부 정보 포함)
LEAKY_MESSAGE = (
    '<HttpError 403 when requesting '
    'https://sheets.googleapis.com/v4/spreadsheets/1AbCdEf_INTERNAL_SHEET_ID/values/'
    'A1?alt=json returned "The caller does not have permission". '
    'Details: "user@example.com lacks sheets.spreadsheets permission">'
)


class _FakeResp:
    def __init__(self, status):
        self.status = status


class _HttpError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.resp = _FakeResp(status)


# ── friendly_error 동작 ───────────────────────────────────────────────────

def test_friendly_error_does_not_leak_exception_text():
    exc = _HttpError(403, LEAKY_MESSAGE)
    msg = friendly_error(exc, "시트에 접근하지 못했습니다")

    assert "INTERNAL_SHEET_ID" not in msg
    assert "user@example.com" not in msg
    assert "sheets.googleapis.com" not in msg
    assert "HttpError" not in msg
    assert "시트에 접근하지 못했습니다" in msg


@pytest.mark.parametrize("status,fragment", [
    (401, "다시 로그인"),
    (403, "권한"),
    (404, "찾을 수 없습니다"),
    (429, "너무 많습니다"),
    (503, "불안정"),
])
def test_friendly_error_maps_status_to_guidance(status, fragment):
    msg = friendly_error(_HttpError(status, LEAKY_MESSAGE), "작업에 실패했습니다")
    assert fragment in msg


def test_friendly_error_falls_back_to_generic_message():
    msg = friendly_error(ValueError("unexpected internal detail /srv/app/secret.py"), "")
    assert msg == GENERIC_MESSAGE
    assert "secret.py" not in msg


def test_http_status_extracts_from_resp():
    assert http_status(_HttpError(404, "not found")) == 404


def test_http_status_extracts_from_message_when_no_attribute():
    assert http_status(Exception("<HttpError 429 when requesting ...>")) == 429


def test_http_status_returns_none_for_plain_exception():
    assert http_status(ValueError("no status here")) is None


# ── 정적 검사: 예외 원문 포맷팅이 남아 있지 않은지 ────────────────────────

# f"...{e}" / f"...{err_str}" / error = str(e) 형태를 잡는다
_LEAK_PATTERNS = [
    re.compile(r'f"[^"]*\{\s*e\s*\}'),
    re.compile(r'f"[^"]*\{\s*err_str\s*\}'),
    re.compile(r'(error|load_error)\s*=\s*str\(\s*e\s*\)'),
]


def _route_sources():
    for path in sorted((REPO_ROOT / "routes").glob("*.py")):
        yield path, path.read_text(encoding="utf-8")


def test_no_raw_exception_in_user_facing_messages():
    offenders = []
    for path, src in _route_sources():
        for lineno, line in enumerate(src.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for pattern in _LEAK_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "예외 원문이 사용자 메시지에 포함됨:\n" + "\n".join(offenders)


def test_templates_do_not_render_raw_error_strings():
    """load_error 는 이미 정제된 문구이므로 템플릿에서 중복 접두어를 붙이지 않는다."""
    src = (REPO_ROOT / "templates" / "list.html").read_text(encoding="utf-8")
    assert "목록을 불러오지 못했습니다: {{ load_error }}" not in src
