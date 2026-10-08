"""로그인 화면의 '컬러로 세계여행' 테스트 참여 링크 (TASK-2026-008 CR-03).

외부 퍼즐 게임 서비스의 참여 페이지로 가는 top-level 링크만 만든다. 링크 계약을
이 모듈에 격리해 앱의 인증·세션·Google Sheets 흐름과 분리한다.

- origin 과 경로는 승인된 값으로 고정한다. campaign ID 만 환경 변수
  `COLOR_WORLD_APP_CAMPAIGN_ID` 로 받아, 이미지 재빌드 없이 Cloud Run 설정만으로
  바꿀 수 있다.
- 값이 없거나 형식이 맞지 않으면 `None` 을 돌려 버튼을 숨긴다(fail-closed).
  코드에 기본 campaign ID 를 두지 않는다.
- 외부 서비스를 조회하지 않으며, 사용자 정보·쿠키·토큰·추적값을 붙이지 않는다.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlencode

CAMPAIGN_ENV = "COLOR_WORLD_APP_CAMPAIGN_ID"

PLAYTEST_COLLECT_URL = "https://ccatlas-f1-459669244480.asia-northeast3.run.app/collect.html"

# 외부 서비스의 CAMPAIGN_ID_PATTERN 과 같은 형식 + 기존 앱 채널 접미사.
_CAMPAIGN_ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{2,40}")
_APP_CHANNEL_SUFFIX = "-app"


def build_app_playtest_url(campaign_id: str | None) -> str | None:
    """기존 앱 채널 campaign ID 로 참여 링크를 만든다. 무효하면 `None`."""
    value = (campaign_id or "").strip()
    if not _CAMPAIGN_ID_PATTERN.fullmatch(value) or not value.endswith(_APP_CHANNEL_SUFFIX):
        return None
    return f"{PLAYTEST_COLLECT_URL}?{urlencode({'campaign': value})}"


def app_playtest_url_from_env() -> str | None:
    """요청 시점의 환경 변수로 참여 링크를 만든다."""
    return build_app_playtest_url(os.environ.get(CAMPAIGN_ENV))
