"""공개 문서(개인정보처리방침·이용약관)에 들어가는 운영 주체 정보 (P0-4).

운영자명·연락처는 개인정보에 해당하므로 저장소에 하드코딩하지 않고 환경 변수로
주입한다 (`.claude/rules/security.md` "No Hardcoding"). 값이 비어 있으면 화면에
플레이스홀더와 "설정 필요" 안내가 노출되므로, 배포 전에 누락을 알아챌 수 있다.

필요한 환경 변수는 `.env.example` 과 `SETUP.md` 에 정리되어 있다.
"""

from __future__ import annotations

import os

# (환경 변수, 화면 표시용 이름, 미설정 시 표시할 플레이스홀더)
_FIELDS = (
    ("operator", "SERVICE_OPERATOR", "운영 주체", "[운영 주체 미설정]"),
    ("contact_email", "PRIVACY_CONTACT_EMAIL", "개인정보 문의 이메일", "[문의 이메일 미설정]"),
    ("service_url", "SERVICE_URL", "서비스 주소", "[서비스 주소 미설정]"),
    ("effective_date", "POLICY_EFFECTIVE_DATE", "시행일", "[시행일 미설정]"),
)

# 이 값들이 비어 있으면 Google OAuth 앱 검증 제출 요건(P0-2)을 충족하지 못한다.
REQUIRED_KEYS = ("operator", "contact_email", "service_url", "effective_date")


def policy_context() -> dict:
    """방침·약관 템플릿에 넘길 컨텍스트를 만든다.

    반환 형태::

        {
            "operator": "표시할 값",
            ...,
            "missing": [{"key": ..., "env": "SERVICE_OPERATOR", "label": "운영 주체"}],
            "is_complete": bool,
        }
    """
    values: dict = {}
    missing: list[dict] = []

    for key, env_name, label, placeholder in _FIELDS:
        raw = (os.environ.get(env_name) or "").strip()
        values[key] = raw or placeholder
        if not raw:
            missing.append({"key": key, "env": env_name, "label": label})

    values["missing"] = missing
    values["is_complete"] = not missing
    return values
