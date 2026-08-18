"""테스트 실행 환경 격리.

배경
    각 테스트 모듈은 `os.environ.setdefault()` 로 테스트용 값을 넣는다.
    그런데 개발자 셸에 실제 값이 이미 export 되어 있으면(예: 로컬 실행을
    위해 `set -a; source .env` 를 한 경우) `setdefault` 는 아무 일도 하지
    않는다. 그 결과

    - 테스트가 실제 클라이언트 ID 와 비교하다가 실패하고,
    - 실패 메시지에 실제 자격증명 값이 그대로 출력된다.

    (`.claude/rules/security.md` "Sanitization" 위반)

    또한 `app.py` 의 `load_dotenv()` 는 기본적으로 기존 환경 변수를
    덮어쓰지 않으므로, 여기서 먼저 고정해 두면 `.env` 값이 테스트로
    새어 들어오지 않는다.

conftest.py 는 테스트 모듈보다 먼저 로드되므로, 모듈 임포트 시점에 환경
변수를 읽는 코드(app.py · routes.auth 등)에도 이 값이 적용된다.
"""
import os
import sys
from pathlib import Path

# 저장소 루트를 import 경로에 넣어 `pytest` 를 직접 실행해도(= `python -m`
# 없이) `app` · `services` · `routes` 를 임포트할 수 있게 한다.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# setdefault 가 아니라 강제 지정한다. 셸에 남아 있는 실제 값보다 우선한다.
TEST_ENV = {
    "APP_ENV": "development",
    "FLASK_SECRET_KEY": "test-flask-secret",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "REDIRECT_URI": "http://localhost:8090/auth/callback",
    # user_key 생성용 HMAC 키. 실제 키가 새어 들어오면 기대값이 달라진다.
    "USER_KEY_HMAC_SECRET": "t" * 48,
    # 실제 TMDb 키가 있으면 외부 호출이 발생할 수 있으므로 비운다.
    "TMDB_API_KEY": "",
    "SESSION_LIFETIME_HOURS": "12",
    "TMDB_ENRICH_CHUNK": "15",
}

for _key, _value in TEST_ENV.items():
    os.environ[_key] = _value
