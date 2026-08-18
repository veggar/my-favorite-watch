@../agent-hub/CLAUDE.md
@PRD.md
@.claude/AGENTS.md
@.claude/rules/coding.md
@.claude/rules/security.md
@.claude/rules/tech-stack.md
@.claude/rules/ui-ux-standards.md

# My Favorite Watch

이 문서는 프로젝트 특화 보완 지침만 관리한다. 전역 지침, 공통 agent, 공통 command, 공통 rules는 `@../agent-hub/CLAUDE.md`를 기준으로 따른다.

## Core Directives

- 요구사항이 모호하거나 실행 기준이 불분명하면 작업을 진행하기 전에 확인 질문을 한다.
- 요구사항 간 충돌이 있으면 임의로 한쪽을 폐기하지 않고, 일관된 해석안을 제안한 뒤 확인한다.
- 복잡한 문제는 더 작은 하위 작업으로 나누어 진행하고, 각 단계의 결과가 다음 단계에 필요한 입력을 제공하도록 정리한다.
- 작업 중 세운 가정, 확인하지 못한 제약, 남은 리스크는 결과 보고에 명시한다.

## 로컬 지침

- 비즈니스 로직과 기능 정의는 `PRD.md`를 기준으로 확인한다.
- Google 로그인, Google Sheets 연동, TMDb 연동, CSV 가져오기, 목록/검색/정렬/필터, 등록/수정/삭제 흐름의 데이터 정합성을 우선한다.
- 민감한 인증 정보, OAuth 토큰, 세션, Google API 권한 변경은 보안 지침과 실제 OAuth 흐름을 함께 검토한다.
- 프로젝트 로컬 세부 지침은 이 문서 상단의 로컬 import를 통해 함께 로드한다.

## 버전 관리

버전 형식은 `v{major}.{minor}.{patch}`이며 `version.py`에서 관리한다. 소스 변경이 포함된 커밋 전에는 변경 유형에 맞춰 버전을 함께 갱신한다.

## 브랜치 · PR 규칙

- **PR 생성 시 base 브랜치를 항상 명시한다.** `gh pr create` 는 현재 체크아웃된
  브랜치의 upstream 이나 저장소 기본 브랜치를 base 로 추정하므로, 생략하면
  의도하지 않은 브랜치로 PR 이 열린다.

  ```bash
  gh pr create --base master --head <branch> --title "..." --body "..."
  ```

- **작업 브랜치는 `master` 에서 딴다.** 다른 작업 브랜치 위에 브랜치를 쌓지 않는다.
  선행 작업이 필요하면 선행 PR 을 master 로 먼저 머지한 뒤 `master` 를 다시 받아 시작한다.

  > 실제 사고 사례: `p0-1 → p0-3 → p0-5 → p0-6` 이 서로 스택된 상태에서
  > PR #6·#7·#8 이 master 가 아니라 바로 앞 작업 브랜치로 머지되었다.
  > master 에는 P0-1 만 들어갔고 P0-3·P0-5·P0-6 이 체인 안에 갇혔는데,
  > PR 목록에는 전부 "Merged" 로 보여 반영된 것으로 오판하기 쉬웠다.

- PR 을 열기 전에 base 대비 상태를 확인한다.

  ```bash
  git fetch origin
  git log --oneline origin/master..<branch>   # 반영될 커밋
  git log --oneline <branch>..origin/master   # 뒤처진 커밋
  ```

- 머지 후에는 해당 브랜치가 실제로 master 조상이 되었는지 검증한다.

  ```bash
  git merge-base --is-ancestor origin/<branch> origin/master && echo 반영됨 || echo 미반영
  ```

## 명령어

* 설치 방법은 아래 "Install:" 섹션에, 실행 명령은 "Run:" 섹션에 작성한다(이 줄은 변경하지 않는다).
* 프로젝트의 설치 및 실행 절차를 명확히 문서화한다.(이 줄은 변경하지 않는다).
* 설치 또는 실행 문서가 없거나, 오래되었거나, 실제 설정과 일치하지 않으면 작업을 진행하기 전에 생성하거나 업데이트한다.(이 줄은 변경하지 않는다).
* 명령어를 업데이트할 때는 필요한 환경 변수, 포트, 진입점, 사전 준비 단계를 명확히 적는다.(이 줄은 변경하지 않는다).
  - **Install:** `pip install -r requirements.txt` (개발/테스트: `pip install -r requirements-dev.txt`)
  - **Run:** `python3 app.py` -> <http://localhost:8090>
    - 사전 준비: `.env.example`을 `.env`로 복사 후 `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `FLASK_SECRET_KEY` / `REDIRECT_URI` 입력. 로컬은 `APP_ENV=development`.
    - `USER_KEY_HMAC_SECRET`(사용자 식별 키): 로컬 미설정 시 개발 전용 고정 키로 폴백한다. 운영은 Secret Manager 주입이 필수이며 미설정 시 로그인이 실패한다.
    - (선택) `TMDB_API_KEY` 미설정 시 TMDb 자동 보강만 생략된다.
    - (선택) `SESSION_LIFETIME_HOURS`(기본 12), `TMDB_ENRICH_CHUNK`(기본 15)
  - **Test:** `python3 -m pytest tests/ -v`
  - **Deploy:** `bash scripts/deploy.sh` (Cloud Run. `.env` 필요. 대상 변경은 `GOOGLE_CLOUD_PROJECT`/`CLOUD_RUN_REGION`)
  - **설정 가이드:** 환경 구성 · Firestore · 배포 후 1회성 설정(TTL 정책 등)은 `SETUP.md` 참조
