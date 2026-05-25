@../agent-hub/.claude/AGENTS.md
@PRD.md
@.claude/AGENTS.md
@.claude/rules/coding.md
@.claude/rules/security.md
@.claude/rules/tech-stack.md
@.claude/rules/ui-ux-standards.md

# My Favorite Watch

이 문서는 프로젝트 특화 보완 지침만 관리한다. 전역 지침, 공통 agent, 공통 command, 공통 rules는 `@../agent-hub/.claude/AGENTS.md`를 기준으로 따른다.

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

## 명령어

* 설치 방법은 아래 "Install:" 섹션에, 실행 명령은 "Run:" 섹션에 작성한다(이 줄은 변경하지 않는다).
* 프로젝트의 설치 및 실행 절차를 명확히 문서화한다.(이 줄은 변경하지 않는다).
* 설치 또는 실행 문서가 없거나, 오래되었거나, 실제 설정과 일치하지 않으면 작업을 진행하기 전에 생성하거나 업데이트한다.(이 줄은 변경하지 않는다).
* 명령어를 업데이트할 때는 필요한 환경 변수, 포트, 진입점, 사전 준비 단계를 명확히 적는다.(이 줄은 변경하지 않는다).
  - **Install:** `pip install -r requirements.txt`
  - **Run:** `python3 app.py` -> <http://localhost:8090>
