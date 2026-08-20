#!/usr/bin/env python3
"""개인정보처리방침·이용약관 콘텐츠를 바꾸기 전, 현재 라이브 버전을 얼려 보관한다.

PRD §5.1: "개인정보처리방침 변경 시 시행일과 이전 버전을 함께 제공한다."

사용법 (콘텐츠를 수정하기 **전에** 실행)::

    python3 scripts/archive_policy_snapshot.py privacy
    python3 scripts/archive_policy_snapshot.py terms
    python3 scripts/archive_policy_snapshot.py both

현재 `.env`에 설정된 `POLICY_EFFECTIVE_DATE`를 파일명으로 써서
`docs/legal/history/{privacy,terms}/{effective_date}.html`에 저장한다.
같은 시행일로 이미 저장된 스냅샷이 있으면 실패한다 — 시행일이 바뀌지
않았는데 다시 아카이브하려는 것은 대개 실수다.

운영 데이터가 필요 없으므로 실제 Google 자격증명 없이, Flask 테스트
클라이언트로 `/privacy`·`/terms`를 그대로 렌더링해 저장한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 앱 임포트 전에 최소한의 필수 환경 변수를 채운다. 실제 배포 값이 아니어도
# 되는 것들은 개발용 더미로 채우고, 정책 문서 값은 .env를 그대로 쓴다.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FLASK_SECRET_KEY", "archive-script-dummy-secret")
os.environ.setdefault("USER_KEY_HMAC_SECRET", "archive-script-dummy-hmac-key-32bytes")
os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy")
os.environ.setdefault("REDIRECT_URI", "http://localhost:8090/auth/callback")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("doc_type", choices=("privacy", "terms", "both"))
    args = parser.parse_args()

    import app as app_module
    from services.site_info import policy_context
    from services import policy_history

    ctx = policy_context()
    effective_date = ctx["effective_date"]
    if not ctx["is_complete"]:
        print(f"⚠️  운영 주체 정보가 미완성 상태입니다: "
              f"{', '.join(m['env'] for m in ctx['missing'])}", file=sys.stderr)
        print("   미완성 상태의 화면을 그대로 보관합니다. 계속하려면 Enter, "
              "중단하려면 Ctrl+C.", file=sys.stderr)
        input()

    targets = ["privacy", "terms"] if args.doc_type == "both" else [args.doc_type]
    client = app_module.app.test_client()

    ok = True
    for doc_type in targets:
        resp = client.get(f"/{doc_type}")
        if resp.status_code != 200:
            print(f"❌ /{doc_type} 렌더링 실패: HTTP {resp.status_code}", file=sys.stderr)
            ok = False
            continue
        try:
            path = policy_history.write_version(
                doc_type, effective_date, resp.get_data(as_text=True)
            )
        except FileExistsError as e:
            print(f"❌ {e}", file=sys.stderr)
            print("   시행일이 이미 바뀌었는지, 또는 재실행이 실수는 아닌지 확인하세요.",
                  file=sys.stderr)
            ok = False
            continue
        print(f"✅ {doc_type}: {path.relative_to(ROOT)}")

    if ok:
        print("\n이제 콘텐츠와 POLICY_EFFECTIVE_DATE를 갱신해도 됩니다.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
