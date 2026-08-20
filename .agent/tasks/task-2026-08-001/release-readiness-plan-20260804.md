# My Favorite Watch — 일반 사용자 제공 준비 작업 계획서

- 작성일: 2026-08-04
- 기준 버전: v1.2.0 (브랜치 `claude/sheet-connection-flow`)
- 기준 문서: PRD.md, CLAUDE.md, `.claude/rules/*`
- 검증 방식: PRD §20 완료 기준을 실제 코드와 1:1 대조

> **현행 기준(2026-08-21):** `master` = `origin/master` = `8b12ed7`, 버전
> `v1.8.0`. 1~6장은 v1.2.0 당시의 문제 분석과 실행 계획을 보존한 역사적
> 기준이며, 현재 완료 판정과 남은 작업은 **7장 진행 상황 업데이트**를 따른다.

---

## 1. 현재 구현 상태 요약

PRD §20 완료 기준 항목은 **기능적으로 모두 구현되어 있다.** 코드 대조로 확인한 주요 근거는 다음과 같다.

| PRD 완료 기준 | 상태 | 근거 |
| - | - | - |
| Google 로그인 (PKCE) | ✅ | `routes/auth.py` `_build_flow` / `auth_callback` |
| 시트 신규 생성 / URL 연결 | ✅ | `routes/sheet.py` `_create_new_spreadsheet` / `_connect_by_url` |
| 목록 조회 · 검색 · 필터 · 정렬 8종 | ✅ | `routes/main.py` `_apply_filters_and_sort` |
| 등록 / 수정 (TMDb 연동 포함) | ✅ | `routes/item.py` `create` / `update` / `tmdb_update` |
| 수정 충돌 방지 (optimistic locking) | ✅ | `services/google_sheets.py` `update_item` |
| 삭제 → `삭제` 워크시트 이관 + 복구 | ✅ | `routes/item.py` `delete` / `restore` |
| 행 식별 | ✅ | `id`(UUID) 컬럼 사용 — 행 번호 기반이 아니므로 다기기 오삭제 위험 없음 |
| 타 시트 / CSV / Excel 가져오기 | ✅ | `routes/sheet.py` `import_sheet` / `upload_csv` |
| CSRF · 세션 쿠키 보안 | ✅ | `app.py` `validate_csrf`, `app.config.update(...)` |
| Firestore refresh_token 영구 세션 | ✅ | `app.py` `auto_restore_session` |
| Cloud Run 배포 구성 | ✅ | `Dockerfile`, `scripts/deploy.sh` |

이번 브랜치에서 추가로 해결한 항목:

- 재로그인 시 시트 연결 정보 유지 (`save_session`의 빈 값 덮어쓰기 버그 수정)
- 기본 시트 탐색 후 사용자 확인 → 수동 설정 → 성공 시 자동 이동 / 실패 시 재시도 플로우

**결론: 남은 작업은 기능 추가가 아니라 "일반 사용자에게 공개해도 안전한 상태 만들기"다.**

---

## 2. P0 — 출시 차단 항목

### P0-1. 세션 쿠키에 `client_secret`·`refresh_token` 저장 (최우선)

- **현황**: `routes/auth.py:83`에서 `session["credentials"]`에 `client_secret`과 `refresh_token`을 함께 저장한다. `app.py:100`의 세션 복원 경로도 동일하다.
- **문제**: Flask 세션 쿠키는 **서명만 되고 암호화되지 않는다.** 쿠키 값을 base64 디코드하면 **OAuth 클라이언트 시크릿 원문이 그대로 읽힌다.** 시크릿은 서버 환경 변수에만 존재해야 한다 (`.claude/rules/security.md` "No Hardcoding" / "Sanitization" 위배).
- **작업**:
  1. `session["credentials"]`에서 `client_secret`, `client_id`, `token_uri`, `scopes` 제거 — 이 값들은 `get_credentials()`에서 환경 변수·상수로 재구성한다
  2. `refresh_token`은 이미 Firestore에 있으므로 세션에서 제거하고, 갱신 시 `device_id`로 Firestore에서 조회
  3. 세션에는 `token`(access token)만 유지
  4. `routes/sheet.py`의 `enrich_items_background`에 넘기는 `creds_data`도 동일하게 정리
- **부수 효과**: 기존 로그인 세션은 무효화되므로 배포 시 재로그인이 필요하다는 점을 안내한다.

### P0-2. OAuth 앱 프로덕션 게시 및 검증 (외부 일정 · 임계 경로)

- **현황**: OAuth 동의 화면이 테스트 모드로 추정된다 (`.env.example` 기준 개인 프로젝트 구성).
- **문제**: 테스트 모드는 (1) 테스트 사용자 100명 제한, (2) **refresh token이 7일 후 만료**되어 Firestore 자동 세션 복원(PRD §4.2)이 일반 사용자에게 동작하지 않는다.
- **작업**:
  1. OAuth 동의 화면 "프로덕션" 게시
  2. `spreadsheets`, `drive.metadata.readonly`는 민감 스코프 → Google 앱 검증 신청 (홈페이지 URL, 개인정보처리방침 URL, 스코프 사용 사유 필요)
  3. `prompt="consent"` 고정(`routes/auth.py:56`) 개선 — Firestore 레코드가 있으면 `select_account`로 전환해 매 로그인 동의 화면 반복을 제거
- **소요**: 코드 변경 소 / 외부 절차 대(통상 2~6주). **오늘 착수 권장.**

### P0-3. 백그라운드 TMDb 보강이 배포 환경에서 유실됨

- **현황**: `routes/sheet.py:212, 310`에서 `threading.Thread(daemon=True)`로 TMDb 보강을 실행한다. 진행 상태는 `services/tmdb_tracker.py`의 **프로세스 메모리 dict**(`_statuses`)에 저장된다. `Dockerfile`은 `gunicorn --workers 2 --threads 8`로 기동한다.

#### 원인 3가지 (심각도 순)

1. **gunicorn 워커 2개 — 인스턴스가 1개여도 발생**
   `--workers 2`는 프로세스를 2개 fork하므로 `_statuses` dict가 **워커별로 따로 존재**한다. 보강 스레드는 가져오기 요청을 처리한 워커에서 실행되지만, 이후 `/item/tmdb-status` 폴링은 두 워커에 분산되므로 **약 50% 확률로 빈 상태가 반환**된다. 진행률 배너가 깜빡이거나 멈춘 것처럼 보인다.
   → **Cloud Run 설정과 무관하게 로컬 다중 워커 환경에서도 재현되는 기존 버그다.**

2. **Cloud Run CPU 스로틀링 — 작업 자체가 중단됨**
   Cloud Run은 응답 반환 후 CPU를 거의 0으로 스로틀링한다(CPU always-allocated 미설정 시). 데몬 스레드가 **중단되고 데이터가 조용히 유실**된다. 가져오기 직후 "TMDb 검색 중..." 배너만 남고 끝나지 않는다.

3. **인스턴스 수평 확장**
   인스턴스가 2개 이상이면 상태 조회가 다른 인스턴스로 라우팅되어 진행 상태를 찾지 못한다. 원인 1과 동일한 문제가 인스턴스 단위로 확대된 것이다.

#### 단기 처방 (즉시 적용 · 코드 변경 최소)

원인 1~3을 모두 회피하여 "단일 프로세스 안에서만 상태를 공유"하도록 강제한다.

1. `Dockerfile` — 워커를 1개로 고정 (스레드는 유지하므로 동시 요청 처리에는 영향 적음)

   ```diff
   - CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 2 --threads 8 --timeout 60 app:app
   + CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --threads 8 --timeout 60 app:app
   ```

2. `scripts/deploy.sh` — CPU 상시 할당 + 인스턴스 1개 고정

   ```diff
     gcloud run deploy "$SERVICE" \
       --source . \
   +   --no-cpu-throttling \
   +   --max-instances 1 \
       --region "$REGION" \
   ```

- **트레이드오프 (반드시 인지할 것)**
  - `--no-cpu-throttling`은 요청 처리 시간이 아닌 **인스턴스 수명 기준 과금**으로 바뀌어 유휴 비용이 증가한다.
  - `--max-instances 1`은 처리량 상한을 만들고, 새 리비전 배포 시 짧은 다운타임이 발생할 수 있다.
  - 어디까지나 **사용자 수가 적은 초기 단계용 임시 조치**이며, 상태를 프로세스 메모리에 두는 구조 자체는 남아 있다.

#### 근본 해결 (2단계 이행 권장)

- **1단계 — 진행 상태 저장소 교체 (작고 안전, 우선 적용)**
  `services/tmdb_tracker.py`의 `_statuses` dict를 Firestore 컬렉션(예: `tmdb_jobs`, 문서 ID = `item_id`)으로 교체한다. 인터페이스(`mark_pending` / `set_status` / `get_statuses` / `clear`)가 이미 함수로 캡슐화되어 있어 **호출부 변경 없이 내부 구현만 교체**할 수 있다. 이것만으로 원인 1과 3이 해소되고, 위 단기 처방 중 `--workers 1` / `--max-instances 1` 제약을 풀 수 있다. 완료된 문서는 TTL로 정리한다.

- **2단계 — 작업 실행 외부화 (원인 2 해소)**
  보강 작업을 요청 수명에서 분리한다.
  - **Cloud Tasks** (권장): 가져오기 시 item 단위 태스크를 큐에 넣고, 앱에 `/tasks/tmdb-enrich` 엔드포인트를 추가해 처리한다. 재시도·실패 가시성·rate limit 제어(PRD §9.6의 0.1초 지연)를 큐 설정으로 위임할 수 있다.
  - **대안**: 대량 가져오기 시 동기 처리 + 진행률 표시로 단순화. 사용자를 기다리게 하지만 유실이 구조적으로 불가능해진다. 건수가 적다면 가장 단순한 해법이다.

  2단계 완료 후에는 `--no-cpu-throttling`을 되돌려 비용을 회수한다.

#### 검증

- 재현 테스트 선행 (`.claude/rules/coding.md` Test-Driven Fixes)
  - 워커 2개로 기동 후 `get_statuses`가 다른 프로세스의 상태를 못 읽는 것을 확인 → 저장소 교체 후 통과하도록
- 배포 환경에서 100건 이상 CSV 가져오기 → 모든 항목이 `done` 또는 `not_found`로 수렴하는지, 페이지를 새로고침해도 진행률이 유지되는지 확인

### P0-4. 개인정보처리방침 / 이용약관 페이지

- **현황**: 없음.
- **문제**: 일반 사용자 대상 서비스의 기본 요건이며 P0-2의 Google 검증 **필수 제출 항목**이다.
- **작업**: `/privacy`, `/terms` 추가. 수집 항목(email, 이름, 프로필 이미지, refresh token), 저장 위치(Firestore, 사용자 본인 Google Sheet), 보관 기간(device_id 쿠키 90일), 삭제 방법(로그아웃), TMDb 외부 API 사용 사실 명시. 로그인 화면 하단에 링크.

### P0-5. 세션 수명 미설정

- **현황**: `app.py:94`에서 `session.permanent = True`를 설정하지만 `PERMANENT_SESSION_LIFETIME`이 없어 **Flask 기본값 31일**이 적용된다.
- **문제**: 세션 쿠키에 토큰이 담긴 현재 구조(P0-1)에서 31일은 과도하다. PRD에도 수명 기준이 없다.
- **작업**: `PERMANENT_SESSION_LIFETIME`을 명시(예: 12시간)하고 PRD §4.2에 기준을 기록한다. 장기 지속은 Firestore + `device_id`(90일)가 담당하므로 사용자 체감 로그인 유지에는 영향이 없다.

### P0-6. 예외 원문이 화면에 노출됨

- **현황**: `routes/settings.py:42,52`, `routes/sheet.py:273`이 `f"...실패: {e}"` 형태로 예외 문자열을 그대로 렌더링한다.
- **문제**: Google API 오류 본문에 내부 식별자·요청 정보가 포함될 수 있다 (security.md "Sanitization").
- **작업**: `routes/sheet.py`의 `_friendly_sheet_error()`와 동일한 방식으로 사용자용 메시지와 서버 로그를 분리한다. (`/connect` 경로는 이번 브랜치에서 이미 적용 완료)

---

## 3. P1 — 안정성 · 품질

| # | 항목 | 내용 |
| - | - | - |
| P1-1 | 테스트 부재 | 테스트 코드 0건 (`.claude/rules/coding.md` Coverage 규칙 위반). pytest 도입 후 우선 대상: 시트 연결 플로우, 재로그인 시 시트 복원, CSV/Excel 파싱, 필터·정렬, optimistic locking 충돌, 삭제→복구 왕복 |
| P1-2 | OAuth 콜백 오류 처리 | 사용자가 동의 화면에서 "거부"하면 `error=access_denied`로 `fetch_token`이 예외를 던져 500으로 빠진다. 콜백 진입 시 `error` 파라미터 검사 → 로그인 화면 + 재시도 안내 (PRD §17 취지) |
| P1-3 | Firestore 세션 수명 관리 | `device_id` 쿠키는 90일이지만 Firestore `sessions` 문서는 영구 잔존(refresh token 포함). `updated_at` + 90일 TTL 정책 설정 (콘솔 설정, 코드 변경 불필요) |
| P1-4 | 이메일 기준 조회 인덱스 | 이번에 추가한 `lookup_saved_sheet`의 email fallback은 단일 필드 equality 쿼리라 기본 인덱스로 동작하지만, 문서 수 증가 시 `limit(20)` 내 정렬이 부정확해질 수 있다. 필요 시 `email` + `updated_at` 복합 인덱스 추가 |
| P1-5 | 대용량 시트 성능 | 조회·등록마다 워크시트 전체를 읽는다. 지원 상한(예: 2,000행) 문서화 후, 중복 검사용 조회를 필요한 열로 축소 |
| P1-6 | 문서 최신화 | SETUP 성격의 사용자 안내 문서 부재. `.env.example`은 최신이나 일반 사용자용 도움말이 없음 |
| P1-7 | TMDb 키 미설정 시 동작 | `TMDB_API_KEY` 없으면 조용히 건너뛴다. 설정 화면에 "TMDb 연동 비활성" 상태를 노출해 사용자가 원인을 알 수 있게 한다 |

---

## 4. P2 — UX 개선

| # | 항목 | 내용 |
| - | - | - |
| P2-1 | PWA 대응 | favicon, manifest.json, 홈화면 아이콘 부재. 모바일 웹앱 표방 대비 미비 |
| P2-2 | 초기 로딩 표시 | `.claude/rules/ui-ux-standards.md` §1 "Now Loading" 좌상단 표시 미구현 |
| P2-3 | 삭제 확인 UI | 네이티브 `confirm()` → 앱 스타일 모달로 교체 |
| P2-4 | 가져오기 안전장치 | 가져오기 전 영향 범위(추가/건너뜀 건수) 확인 단계 강화 |
| P2-5 | 다국어 | 현재 한국어 고정. 확장 시 ui-ux-standards §3 언어 규칙(en fallback) 적용 |

---

## 5. 실행 로드맵

| 단계 | 기간(안) | 내용 | 완료 기준 |
| - | - | - | - |
| Phase 0 | 즉시 | P0-2 검증 신청 접수 | Google 검증 심사 대기 상태 진입 |
| Phase 1 | 1주 | P0-1, P0-5, P0-6 (보안·세션 정리) | 세션 쿠키에 시크릿·refresh token 미포함 확인 |
| Phase 2 | 1주 | P0-3 단기 처방(워커 1개 + CPU 상시 할당) 즉시 적용 → 1단계(진행 상태 Firestore 이관), P0-4 (정책 페이지) | 배포 환경에서 대량 가져오기 보강 완료 확인, 새로고침 후에도 진행률 유지 |
| Phase 3 | 1~2주 | P1 전체 (P1-1 테스트를 먼저 깔고 진행) | pytest 통과, 문서-실제 일치 |
| Phase 4 | 검증 승인 후 | 프로덕션 게시, 일반 사용자 공개 | 미등록 계정 로그인 및 자동 재로그인 정상 동작 |
| Phase 5 | 상시 | P2 순차 반영 | — |

**작업 규칙** (`.claude/rules/coding.md`):

- 항목별 `claude/{feature-name}` 브랜치 분리, 머지 시 `yyyymmdd_{keyword}` 태그
- 버그성 항목(P0-3, P1-2)은 재현 테스트 선행 작성
- 소스 변경 커밋마다 `version.py` 갱신 — P0 묶음 완료 시 v1.3.0 권장

---

## 6. 리스크 및 전제

- **Google 앱 검증 기간은 통제 불가(통상 2~6주)이며 전체 일정의 임계 경로다.** P0-2를 가장 먼저 착수해야 한다.
- P0-1 적용 시 기존 로그인 세션이 모두 무효화된다. 사용자에게 재로그인 안내가 필요하다.
- P0-3은 3단 대응이다. **단기 처방(워커 1개 + CPU 상시 할당)은 배포 설정만 바꾸면 되지만 비용과 처리량을 희생**하므로 임시 조치로만 사용한다. **1단계(진행 상태를 Firestore로 이관)는 `tmdb_tracker`의 함수 인터페이스가 이미 캡슐화되어 있어 호출부 변경 없이 가능하며 비용도 거의 들지 않으므로 우선 착수 대상이다.** 2단계(Cloud Tasks)는 인프라 추가를 수반하므로 사용량 증가 시점에 전환한다.
- 본 문서는 `id`(UUID) 컬럼이 이미 존재함을 전제로 한다. 행 번호 기반 식별을 도입하는 변경은 다기기 오삭제 위험을 만들 수 있으므로 지양한다.

---

## 7. 진행 상황 업데이트 (2026-08-21)

### 7.1 기준 형상과 배포 상태

- `master`와 `origin/master`는 `8b12ed711d330e084e3fb8e51a53dbd1eaba7dc4`
  (`Merge pull request #16 from veggar/claude/legal-checklist-followup`)로 일치한다.
- 현재 버전은 `v1.8.0`이다.
- PR #15에서 P0-4 코드, P2-1~4와 관련 회귀 테스트가 병합됐다.
- PR #16에서 CSV 가져오기 서버 측 단기 저장(D-1), Firestore TTL 검증·적용(D-2),
  방침·약관 이전 버전 보관(D-3), 연령·공지 정책이 병합됐다.
- Claude CLI 세션 `9c21963d-50d0-487e-8bcb-e830ee03e2c7`에서 남은 구현을
  완료해 `master`에 반영하고 배포했다는 사용자 확인을 받았다. 이 문서 점검에서는
  원격 Git 반영까지 재검증했으며, 실제 Cloud Run 리비전·공개 URL 동작은 별도
  운영 점검 대상으로 구분한다.

### 7.2 P0 상태

| 항목 | 현재 판정 | PRD·master 근거 | 남은 작업 |
| - | - | - | - |
| P0-1 세션 민감정보 분리 | ✅ 완료 | 하이브리드 서버 세션을 사용하고 쿠키에는 `_sid` 등 식별·요청 상태만 둔다. CSV 원문도 `csv_staging_id`로 대체됐다(PRD §4.2, §16.1). | 없음 |
| P0-2 OAuth 프로덕션·검증 | 🟡 부분 완료 | ID Token 검증과 HMAC `user_key`는 완료됐지만 `routes/auth.py`의 `prompt="consent"`가 유지되고, `SETUP.md`는 프로덕션 게시·Google 앱 검증을 여전히 일반 공개 전 요건으로 둔다. | OAuth 프로덕션 게시·앱 검증 결과 확인, 기존 기기 세션이 있을 때 `select_account` 적용 여부 결정 |
| P0-3 TMDb 보강 내구성 | 🟡 코드 완료·운영 검증 필요 | 데몬 스레드 대신 요청 단위 청크 처리, Firestore `tmdb_jobs`, TTL `ACTIVE`가 반영됐다(PRD §9, §16.3). | 배포 환경 100건 이상 가져오기와 새로고침 후 자동 재개 검증 (`SETUP.md` §11) |
| P0-4 개인정보처리방침·이용약관 | 🟡 부분 완료 | `/privacy`, `/terms`, 로그인·설정 링크, 환경 변수 주입, 이전 버전 열람은 구현·배포됐다. PRD §5.1과 §20은 콘텐츠 확정·법률 검토 전까지 부분 완료로 정의한다. | 운영 주체 주소·소재지·준거법 공식 확정, 수탁자·국외 이전 세부정보 확인, 삭제 요청 절차, TMDB 이용조건, 법률 검토, 실제 공개 판정 |
| P0-5 세션 수명 | ✅ 완료 | 기기·서버 세션 90일과 인증 신선도 12시간의 2계층 수명 적용(PRD §4.2). | 없음 |
| P0-6 예외 원문 노출 | ✅ 완료 | `services/errors.py`의 정제 메시지와 서버 로그 분리(PRD §17·§18). | 없음 |

**P0 결론:** 애플리케이션 코드 기준 출시 차단 결함은 해소됐지만, P0-2의 Google
외부 절차와 P0-4의 법률·운영 콘텐츠 확정이 일반 공개 게이트로 남아 있다.

### 7.3 P1 상태

| 항목 | 현재 판정 | 근거와 남은 작업 |
| - | - | - |
| P1-1 테스트 | 🟡 부분 완료 | 프로젝트 `.venv`의 Python 3.14.7에서 전체 191개 테스트가 통과했다(경고 9건). 공개 페이지·PWA·확인 모달·가져오기 계획·CSV 헤더·서버 측 staging·정책 이력 회귀 테스트가 추가됐다. 다만 시트 연결·필터/정렬·낙관적 잠금·삭제/복구의 집중 테스트는 여전히 부족하다. |
| P1-2 OAuth 취소·오류 처리 | ✅ 완료 | `access_denied`와 host/cookie/state/token/identity 실패를 코드화해 처리한다(PRD §4.2). |
| P1-3 Firestore 세션 TTL | ✅ 완료 | `tmdb_jobs`, `device_sessions`, `server_sessions`, `csv_import_staging`의 TTL `ACTIVE`가 2026-08-21 검증·반영됐다(`docs/legal/privacy-policy-draft.md`, 커밋 `fecc784`). |
| P1-4 이메일 인덱스 | ⚪ 조건부 레거시 | 신규 경로는 `user_key` 직접 조회다. 이메일 인덱스는 레거시 `sessions`가 동일 이메일 20건을 넘을 때만 필요한 전환기 작업이다(`SETUP.md` §10.4.1). |
| P1-5 대용량 시트 | 🟡 부분 완료 | 워크시트당 2,000행 지원 상한은 문서화됐지만 전체 읽기 구조와 중복 검사용 열 축소는 남아 있다(`SETUP.md` §12). |
| P1-6 문서 최신화 | ✅ 완료 | `PRD.md`, `SETUP.md`, 법률 초안과 세부 task 문서가 현재 구조를 설명한다. |
| P1-7 TMDb 비활성 표시 | ✅ 완료 | 설정 화면에서 연동 활성·비활성 상태를 표시한다(PRD §14). |

### 7.4 P2 상태

| 항목 | 현재 판정 | 근거와 남은 작업 |
| - | - | - |
| P2-1 PWA | ✅ 완료 | manifest, favicon, Apple/마스커블 아이콘과 공통 head 메타 구현(PRD §20). |
| P2-2 초기 로딩 | ✅ 완료 | 공통 `Now Loading` 표시 구현(PRD §20). |
| P2-3 확인 모달 | ✅ 완료 | 삭제·전체 로그아웃·가져오기에 앱 스타일 확인 모달 적용(PRD §20). |
| P2-4 가져오기 안전장치 | ✅ 완료 | 시트·CSV 가져오기 전에 추가·중복 건수와 영향 범위를 표시(PRD §13, §20). |
| P2-5 다국어 | ⬜ 보류 | 한국어 고정이며 i18n 구조는 도입하지 않았다. 확장 시 영어 fallback 규칙을 적용한다. |

### 7.5 현재 남은 작업 순서

1. **일반 공개 게이트:** P0-4 법률 체크리스트를 확정하고 전문가 검토를 받은 뒤
   `/privacy`, `/terms`를 실제 공개 상태로 승인한다.
2. **Google 외부 게이트:** OAuth 동의 화면 프로덕션 게시·앱 검증 상태를 확인하고
   `prompt="consent"` 반복 동의 개선 여부를 결정한다.
3. **배포 검증:** `SETUP.md` §11의 미등록 계정, 멀티 기기, 쿠키, 100건 이상
   CSV/TMDb 보강과 새로고침 재개 항목을 실제 운영 URL에서 확인한다.
4. **테스트 보완:** Python 3.14.7 가상환경의 191개 테스트는 통과했다. 남은
   핵심 업무 흐름의 집중 테스트를 추가하고 `datetime.utcnow()` 경고 9건을 정리한다.
5. **규모 확장 시:** P1-5 시트 읽기 최적화와 P2-5 다국어를 착수한다.

### 7.6 완료 판정 요약

- **코드 구현:** P0-1·3·5·6, P1-2·3·6·7, P2-1~4 완료
- **부분 완료:** P0-2, P0-4, P1-1, P1-5
- **조건부/보류:** P1-4, P2-5
- **배포:** 사용자 확인 기준 완료, 원격 `master` 반영 확인 완료
- **일반 공개 준비:** PRD 기준 미완료 — Google 외부 검증, 법률 콘텐츠 확정·검토,
  실제 운영 체크리스트 검증 후 최종 완료로 전환
