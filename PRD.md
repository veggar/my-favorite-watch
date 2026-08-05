# My Favorite Watch — 구글 시트 기반 영상 작품 기록 관리 앱 기능 정의서

> 마지막 업데이트: 2026-05-25

---

## 1. 목적

사용자가 Google 계정으로 로그인한 후, 본인의 Google Sheet를 연결하여
영화, 다큐멘터리, 애니메이션, 드라마 등 영상 작품의 관람 기록을 모바일 웹앱에서
조회, 정렬, 등록, 수정, 삭제할 수 있도록 한다.

제목 등록 시 TMDb API를 통해 해당 작품의 공식 링크·공식 평점·원제를 자동으로 연결하며,
링크는 카드 내 🔗 아이콘으로 표시하여 빠른 작품 정보 접근을 가능하게 한다.

---

## 2. 범위

### 2.1 포함 범위

- Google 로그인
- Google Sheet 연결 (신규 생성 / 기존 URL 연결)
- 타 Google Sheet에서 데이터 가져오기
- CSV / Excel 파일 가져오기 (인코딩 자동 감지, 중복 건너뜀)
- 목록 조회
- 검색 (제목 / 전체 필드)
- 카테고리 · 관람 여부 필터
- 정렬 (8가지 기준)
- 등록 (TMDb 자동 연결 포함)
- 수정 (수정 모달, TMDb 수동 업데이트 버튼)
- 삭제 (삭제 워크시트 이관)
- 삭제된 항목 조회 및 복구
- 설정 관리 (문서명 · 워크시트명 변경, 기본 정렬 저장)
- Firestore 기반 refresh_token 영구 세션 복원
- Cloud Run 배포 구성

### 2.2 제외 범위

- 다중 사용자 협업 기능
- 별도 관리자 페이지
- 외부 공유 기능
- 소셜 기능 (팔로우, 댓글 등)
- IMDb / 나무위키 연동 (현재 TMDb 전용)

---

## 3. 데이터 모델

### 3.1 기본 컬럼 (Google Sheet 헤더 순서)

| 컬럼 | 설명 |
|------|------|
| id | 고유 식별자 (UUID v4, 등록 시 자동 생성) |
| title | 작품 제목 |
| titleLink | TMDb 작품 페이지 URL (자동 수집 또는 수동 입력) |
| originalTitle | 원제 (TMDb `original_title` / `original_name`, 자동 수집) |
| genre | 장르 자유 입력 (예: 액션, SF) |
| category | 작품 구분 (영화 / 드라마 / 다큐 / 애니 / 기타) |
| watched | 관람 여부 (true / false 문자열) |
| rating | 개인 평점 (0.0 ~ 5.0, 0.5 단위) |
| officialRating | 공식 평점 (TMDb `vote_average`, 소수점 1자리) |
| watchedAt | 관람 날짜 (ISO 형식, watched=true일 때만 유효) |
| registeredAt | 등록 일시 (ISO, 자동 입력) |
| updatedAt | 수정 일시 (ISO, 자동 갱신) |
| review | 간단 후기 (자유 텍스트) |
| synopsis | 간략한 내용 요약 (자유 텍스트) |

### 3.2 삭제 워크시트 추가 컬럼

- 워크시트명: `삭제`
- 위 14개 컬럼 + `deletedAt` (삭제 일시 ISO)

### 3.3 category 허용값

- 영화 / 드라마 / 다큐 / 애니 / 기타

---

## 4. 인증 및 권한

### 4.1 로그인 방식

- Google OAuth 2.0 (PKCE 지원)
- 필요 스코프: `openid`, `userinfo.email`, `userinfo.profile`, `spreadsheets`, `drive.metadata.readonly`

### 4.2 세션 관리

- Flask 세션에 현재 요청 처리에 필요한 사용자·시트·OAuth 상태 저장
- Firestore `refresh-token` 데이터베이스에 `device_id`별 refresh_token 저장
- `device_id` 쿠키는 HttpOnly / SameSite=Lax / 운영 환경 Secure 옵션으로 90일 유지
- Flask 세션이 비어 있어도 `device_id` 쿠키와 Firestore 저장값으로 Google 인증 세션 자동 복원
- 재로그인 시 Firestore에 저장된 시트 연결 정보를 세션으로 복원한다
- 세션에 시트 정보가 없는 상태에서 Firestore 문서를 갱신할 때 기존 시트 연결 정보를 빈 값으로 덮어쓰지 않는다
- 토큰 만료 시 자동 갱신

#### 세션 수명 기준

수명을 **두 계층으로 분리**한다. 짧은 쪽은 쿠키 탈취 시 노출 창을 줄이고,
긴 쪽이 사용자가 체감하는 로그인 유지 기간을 담당한다.

| 계층 | 값 | 담당 | 근거 |
|----|----|----|----|
| Flask 세션 쿠키 (`PERMANENT_SESSION_LIFETIME`) | **12시간** (환경 변수 `SESSION_LIFETIME_HOURS`) | access token 등 단기 상태 | 만료돼도 아래 계층이 같은 요청에서 세션을 재구성하므로 재로그인이 발생하지 않는다 |
| `device_id` 쿠키 + Firestore `refresh_token` | **90일** | 장기 로그인 유지 | 자주 로그인하는 성격의 앱이 아니므로 동일 디바이스에서 90일 유지를 목표로 한다 |

- Flask 기본값 31일을 그대로 두지 않는다. 값을 명시하지 않으면 의도하지 않은 수명이 적용된다.
- 세션 쿠키 만료 시각은 요청마다 연장된다(`SESSION_REFRESH_EACH_REQUEST`). 사용 중에는 끊기지 않는다.
- `device_id` 쿠키 만료 역시 세션 자동 복원에 성공할 때마다 연장된다. 따라서 90일은 **마지막 사용 시점 기준**이며, 계속 사용하는 사용자는 재로그인 없이 유지된다.
- 90일 이상 미사용 시에만 재로그인이 필요하다.
- 전제: OAuth 동의 화면이 프로덕션으로 게시되어 있어야 한다. 테스트 모드에서는 Google이 refresh token을 7일 후 만료시키므로 위 90일 기준이 성립하지 않는다.

### 4.3 시트 접근 권한

- 사용자가 지정한 Google Sheet에 대해 읽기/쓰기 가능해야 함

### 4.4 설정 완료 조건

- Google 로그인 완료 → Google Sheet 지정 완료 후 목록 화면 진입

---

## 5. 화면 구성

| 화면 | URL 경로 |
|------|---------|
| 로그인 | `/login` |
| 시트 연결/생성 | `/connect` |
| 타 시트 가져오기 | `/import-sheet` |
| CSV 가져오기 | `/upload-csv` |
| 목록 (메인 / 삭제된 항목 탭) | `/` |
| 설정 | `/settings` |

등록 및 수정은 목록 화면 내 슬라이드 업 모달로 처리한다.

---

## 6. 목록 화면 기능

### 6.1 기본 구조

- 상단 고정 헤더: 앱명(My Favorite Watch), 앱 버전, 로그인 계정명, 설정 버튼
- 툴바: 검색창 + 범위 셀렉트 / 카테고리 칩 / 관람 여부 칩 / 정렬 셀렉트 / `+ 등록` 버튼
- 결과 요약 (필터 적용 시 "N개 (전체 M개)")
- 작품 카드 목록
- 탭: 작품 목록 / 삭제된 항목

### 6.2 작품 카드 규칙

각 작품은 독립된 카드로 표시된다.

**카드 1행 (주요 정보)**
- 제목 텍스트
- titleLink가 있으면 🔗 아이콘 (클릭 시 TMDb 페이지 새 탭 열기)
- TMDb 검색 진행 중인 경우 상태 아이콘 (⏳ 대기 / 🔍 검색 중 / ✕ 정보 없음)
- category 배지 (파란 배지)
- genre 배지 (회색 배지, 있을 때만 표시)
- 나의 평점(⭐) / 공식 평점(🎬) — 있을 때만 표시

**카드 2행 (부수 정보)**
- 관람일, 등록일 (작은 흐린 텍스트)

**관람 여부 UI**
- 카드 우측: "✓ 관람 완료" / "♥ 보고 싶어요" 토글 버튼
- 관람 완료: 연한 청록 배경 + 청록 좌측 테두리
- 보고 싶어요: 연한 노랑 배경 + 주황 좌측 테두리
- 전환 즉시 Google Sheet에 AJAX로 반영 (페이지 새로고침 없음)

### 6.3 카드 펼침/접기

- 카드 클릭 시 후기 / 내용 요약 영역 토글
- 펼침 상태에서 수정 버튼 / 삭제 버튼 노출

### 6.4 검색 포커스

- 검색어 입력 후 자동 검색(400ms 디바운스) 실행 후 검색창 포커스 유지
- 카테고리·관람 여부 필터 칩 선택 후에도 검색창 자동 포커스 복귀

### 6.5 가져오기 알림 배너

- CSV / 시트 가져오기 완료 후 목록 상단에 성공 메시지 배너 표시
- TMDb 비동기 검색 진행 중이면 진행률 `N% (M/total)` 실시간 업데이트

---

## 7. 검색 기능

### 7.1 검색 대상

- 기본: `title`
- 전체 검색 모드: `title`, `genre`, `review`, `synopsis`

### 7.2 검색 방식

- 부분 일치, 대소문자 구분 없음
- 검색어 입력 400ms 후 자동 실행 (엔터 불필요)
- ✕ 버튼으로 검색어 즉시 초기화

### 7.3 필터

- category 필터: 전체 / 영화 / 드라마 / 다큐 / 애니 / 기타 (칩 UI)
- 관람 여부 필터: 전체 / 관람 완료 / 보고 싶어요 (칩 UI)

---

## 8. 정렬 기능

| 키 | 표시명 |
|----|--------|
| `registered_desc` | 최근 등록일순 (기본값) |
| `registered_asc` | 오래된 등록일순 |
| `updated_desc` | 최근 수정일순 |
| `title_asc` | 제목 오름차순 |
| `title_desc` | 제목 내림차순 |
| `watched_desc` | 관람일 최신순 |
| `rating_desc` | 평점 높은순 |
| `rating_asc` | 평점 낮은순 |

설정 화면에서 기본 정렬 저장 가능.

---

## 9. TMDb 자동 연결 기능

### 9.1 TMDb API 사용

- `/3/search/movie`, `/3/search/tv` 엔드포인트 사용
- API 키 미설정 시 전체 기능 자동 스킵 (오류 없이 동작)

### 9.2 수집 항목

| 필드 | TMDb 원본 |
|------|-----------|
| titleLink | `https://www.themoviedb.org/{movie|tv}/{id}` |
| officialRating | `vote_average` (소수점 1자리) |
| originalTitle | `original_title` (영화) / `original_name` (TV) |

### 9.3 검색 우선순위

- 드라마 카테고리: TV 검색 우선 → 없으면 영화 검색
- 그 외: 영화 검색 우선 → 없으면 TV 검색

### 9.4 동작 시점

| 시점 | 방식 |
|------|------|
| 신규 등록 (수동) | 저장 시 동기 검색 |
| CSV / 시트 가져오기 | 배치 저장 직후 **비동기 백그라운드** 검색 |
| 수정 모달 "↺ TMDb로 업데이트" 버튼 | AJAX 즉시 검색 후 폼 갱신 |
| 제목 변경 후 저장 | 링크 재검색 여부 확인 팝업 |

### 9.5 비동기 검색 진행 표시

- 목록 카드에 ⏳→🔍 아이콘 실시간 표시 (2초 폴링)
- 검색 완료 시 아이콘 제거, 🔗 아이콘 자동 노출
- TMDb에서 찾지 못한 경우 ✕ 아이콘 표시

### 9.6 Rate Limit

- 배치 처리 시 항목 간 0.1초 대기 (TMDb 40req/10s 제한 준수)

### 9.7 수동 링크 입력

- 사용자가 직접 URL 입력 가능, 자동 검색보다 우선 적용

---

## 10. 등록 기능

### 10.1 진입 방식

- 목록 화면 툴바 `+ 등록` 버튼 → 슬라이드 업 모달

### 10.2 입력 항목

| 항목 | 필수 | 비고 |
|------|------|------|
| title | 필수 | |
| category | 필수 | 영화/드라마/다큐/애니/기타 |
| genre | 선택 | 자유 입력 |
| watched | 필수 | 기본값 false |
| watchedAt | 조건부 | watched=true일 때 입력 가능 |
| rating | 선택 | 0~5, 0.5 단위 슬라이더 |
| officialRating | 선택 | 자동 수집, 수동 수정 가능 |
| originalTitle | 선택 | 자동 수집, 수동 수정 가능 |
| titleLink | 선택 | 자동 검색, 수동 입력 가능 |
| review | 선택 | |
| synopsis | 선택 | |

### 10.3 저장 시 자동 처리

- id (UUID v4) 자동 생성
- registeredAt / updatedAt 자동 입력
- titleLink 미입력 시 TMDb 자동 검색 (동기)

---

## 11. 수정 기능

### 11.1 진입 방식

- 카드 펼침 → 수정 버튼 클릭 → 슬라이드 업 모달

### 11.2 수정 가능 항목

- title, category, genre, watched, watchedAt, rating, officialRating, originalTitle, titleLink, review, synopsis

### 11.3 수정 시 자동 처리

- updatedAt 자동 갱신
- title 변경 감지 시 "링크 재검색 여부" 확인 팝업

### 11.4 "↺ TMDb로 업데이트" 버튼

- 수정 모달에만 표시
- 클릭 시 현재 제목으로 TMDb 즉시 검색
- titleLink, officialRating, originalTitle 폼 필드에 즉시 반영
- 시트에도 즉시 저장

---

## 12. 삭제 기능

### 12.1 삭제 단위

- 작품 단위 삭제 (카드 펼침 → 삭제 버튼 → 확인 팝업)

### 12.2 삭제 처리 방식

- 원본 워크시트에서 행 제거
- `삭제` 워크시트에 복사본 + `deletedAt` 필드 추가 이관

### 12.3 삭제된 항목 복구

- 목록 화면의 `삭제된 항목` 탭에서 삭제 워크시트 데이터를 조회
- 복구 버튼 클릭 시 `삭제` 워크시트의 행을 원본 워크시트로 다시 추가
- 복구된 항목은 `updatedAt`을 복구 시점으로 갱신
- 복구 완료 후 `삭제` 워크시트의 해당 행 제거

---

## 13. 데이터 가져오기

### 13.1 시트 연결/생성 (`/connect`)

연결 화면은 아래 단계로 진행한다.

#### 13.1.1 저장된 연결 정보 우선 사용

- 이전에 연결한 시트 정보가 있으면 연결 화면을 거치지 않고 목록 화면으로 진입한다
- 저장된 연결 정보는 `device_id` 기준으로 우선 조회하고, 해당 기기 기록이 없으면 동일 계정(email)의 가장 최근 연결 정보를 사용한다
- 세션이 만료되어 재로그인한 경우에도 시트를 다시 설정하도록 요구하지 않는다

#### 13.1.2 기본 시트 탐색 및 사용자 확인

- 저장된 연결 정보가 없으면 Google Drive에서 `My Favorite Watch` 이름의 스프레드시트를 검색한다
- 검색 중에는 "기록을 저장할 구글 시트를 확인하고 있습니다." 메시지와 로딩 애니메이션을 표시한다
- 검색되면 자동으로 연결하지 않고 사용자에게 확인을 요청한다
  - 안내: "'My Favorite Watch' 시트를 찾았습니다. 이 시트로 연결할까요?"
  - 선택지: "이 시트로 연결" / "직접 설정하기"
- 검색되지 않으면 곧바로 수동 설정 단계로 이동한다

#### 13.1.3 수동 설정 단계

- 사용자가 "직접 설정하기"를 선택했거나 기본 시트가 검색되지 않은 경우 진입한다
- **기존 시트 연결**: Google Sheet URL 입력 → 접근 권한 확인 → `My Favorite Watch` 워크시트 자동 생성(없는 경우) → 세션에 저장
- **새 시트 생성**: 문서명 + 워크시트명 입력 → Google Drive에 새 문서 생성 → 워크시트 + 헤더 자동 초기화
- 기본 시트가 검색된 상태에서 진입한 경우 "이전" 버튼으로 확인 단계로 돌아갈 수 있다

#### 13.1.4 결과 처리

- 성공 시: "'{시트명}' 시트에 연결되었습니다." 메시지를 잠시 표시한 뒤 별도 조작 없이 목록 화면으로 자동 이동한다
- 실패 시: 자동 이동하지 않고 실패 원인을 화면에 표시한다. "다시 시도" 및 "이전" 버튼을 제공하여 사용자의 다음 입력을 기다린다
- JavaScript를 사용할 수 없는 환경에서는 기존 폼 POST 방식으로 동작한다 (폴백)

### 13.2 타 Google Sheet에서 가져오기 (`/import-sheet`)

1. 소스 시트 URL 입력 → 워크시트 목록 미리보기
2. 가져올 워크시트 선택 후 가져오기 실행
3. **중복 처리**: 제목(소문자) 기준 기존 항목과 비교, 중복 건너뜀
4. 성공 시 즉시 목록으로 리디렉션
5. TMDb 보강은 **비동기 백그라운드** 실행

### 13.3 CSV / Excel 파일 가져오기 (`/upload-csv`)

**지원 파일**

- `.csv`
- `.xlsx`
- `.xls`

**지원 컬럼 형식**

| 컬럼 위치 | 필드 |
|-----------|------|
| 0 | 관람여부 (`v` 또는 `✓` = 관람 완료, 빈값 = 보고 싶어요) |
| 1 | 장르 (카테고리 키워드 자동 추론: 애니/드라마/다큐/교육/역사 등) |
| 2 | 제목 |
| 3 | 평점 (`A+`, `A`, `B+`, `B`, `B-`, `C+`, `C`, `C-` → 숫자 변환) |
| 4 | 등록날짜 (`2020.01.03`, `2021.11.x`, `2025. 11. 23` 등 파싱) |
| 5 | 관람날짜 |
| 6 | 간단후기 |

- 인코딩 자동 감지: utf-8 → utf-8-sig → cp949 → euc-kr 순서
- 첫 행 헤더 자동 감지 및 스킵
- 제목 없는 행 자동 스킵

**가져오기 흐름**

1. CSV 또는 Excel 파일 선택 → 미리보기 (최대 50건) + 요약 통계 (전체/관람/보고싶어요/카테고리별)
2. 등록하기 클릭 → **중복 확인** (기존 제목 소문자 비교) → **배치 저장** (단일 API 호출)
3. 즉시 목록으로 리디렉션 (저장 완료)
4. **비동기 백그라운드**로 TMDb 보강 진행
5. 목록 페이지에서 진행률 실시간 표시

---

## 14. 설정 기능 (`/settings`)

| 기능 | 설명 |
|------|------|
| 계정 정보 표시 | 로그인한 Google 계정 이메일/이름 |
| 연결된 시트 정보 | 문서명 / 워크시트명 |
| 문서명 변경 | Google Drive 문서 이름 변경 |
| 워크시트명 변경 | 워크시트(탭) 이름 변경 |
| 기본 정렬 저장 | 현재 정렬 기준을 기본값으로 저장 |
| 시트 연결 해제 | 세션 시트 정보만 초기화 (데이터 삭제 없음) |
| 로그아웃 | 세션 전체 초기화 |

---

## 15. 유효성 검증

### 15.1 등록/수정 필수값

- title, category, watched

### 15.2 허용 정책

- genre, rating, watchedAt, review, synopsis, titleLink, originalTitle, officialRating은 비필수
- watched=false이면 watchedAt 저장 시 빈 문자열 처리
- rating: 0.0~5.0 범위, 0.5 단위 슬라이더

---

## 16. 상태 관리

### 16.1 세션 저장 항목

| 키 | 내용 |
|----|------|
| `credentials` | Google OAuth 토큰 정보 |
| `user` | 로그인 사용자 이메일/이름/사진 |
| `sheet_id` | 연결된 Google Sheet ID |
| `sheet_title` | 연결된 문서 이름 |
| `worksheet_name` | 연결된 워크시트 이름 |
| `default_sort` | 기본 정렬 키 |
| `csv_import_data` | CSV 파싱 결과 임시 저장 (미리보기 → 등록 사이) |
| `import_success` | 가져오기 완료 메시지 (목록 배너용) |
| `tmdb_pending_ids` | 비동기 TMDb 보강 대기 중인 item_id 목록 |

### 16.2 Firestore 영구 세션 상태 (`services/firestore_session.py`)

| 키 | 내용 |
|----|------|
| `device_id` | 브라우저 식별용 쿠키 값 |
| `email` | 로그인 사용자 이메일 |
| `refresh_token` | Google OAuth refresh_token |
| `user` | 사용자 이메일/이름/사진 |
| `sheet_id` | 연결된 Google Sheet ID |
| `sheet_title` | 연결된 문서 이름 |
| `worksheet_name` | 연결된 워크시트 이름 |
| `updated_at` | Firestore 세션 갱신 시각 |

### 16.3 메모리 상태 (`services/tmdb_tracker.py`)

- 서버 메모리 딕셔너리로 item_id별 TMDb 진행 상태 추적
- 상태값: `pending` / `searching` / `done` / `not_found`
- 서버 재시작 시 초기화됨 (임시 표시용)

---

## 17. 에러 처리

| 케이스 | 처리 방식 |
|--------|----------|
| 로그인 실패 | 재시도 안내 |
| 시트 접근 권한 없음 (403) | "접근 권한이 없습니다" 메시지 |
| 시트 없음 (404) | "시트를 찾을 수 없습니다" 메시지 |
| 목록 로드 실패 | 오류 배너 + 재시도 버튼 |
| TMDb 검색 실패 | 링크 없이 작품 저장, 사용자 알림 없음 |
| CSV 인코딩 불인식 | "UTF-8 또는 EUC-KR 파일 사용 안내" |
| CSRF 검증 실패 | "잘못된 요청입니다. 페이지를 새로고침 후 다시 시도해주세요." 안내 |
| 수정 충돌 | `updatedAt` 비교 후 최신 내용 확인 안내 |

---

## 18. 보안

- Google OAuth 2.0 + PKCE 인증
- OAuth 권한은 Drive 전체 읽기 대신 `drive.metadata.readonly`로 최소화
- 외부 API 키 (TMDb, Google) 는 `.env` 서버 환경 변수 관리
- 클라이언트에 API 키 미노출
- 운영 환경에서 `FLASK_SECRET_KEY` 미설정 시 앱 시작 실패
- POST/PUT/PATCH/DELETE 요청 CSRF 토큰 검증
- 세션 쿠키: HttpOnly, SameSite=Lax, 운영 환경 Secure
- 개발 환경에서만 `OAUTHLIB_INSECURE_TRANSPORT=1` (HTTP 허용), `OAUTHLIB_RELAX_TOKEN_SCOPE=1`

---

## 19. 기술 구현

### 19.1 프레임워크

- **언어**: Python 3.11+ (로컬), Python 3.12-slim (Docker)
- **웹 프레임워크**: Flask 3.x (SSR, Jinja2 템플릿)
- **세션**: Flask 세션 + Firestore refresh_token 영구 저장
- **배포 런타임**: gunicorn + Cloud Run

### 19.2 외부 서비스

| 서비스 | 용도 |
|--------|------|
| Google OAuth 2.0 | 사용자 인증 |
| Google Sheets API v4 | 데이터 읽기/쓰기 |
| Google Drive API | 시트 생성, 문서명 변경 |
| TMDb API v3 | 작품 링크·공식 평점·원제 수집 |
| Firestore | refresh_token 기반 세션 복원 |

### 19.3 주요 패키지

```
flask==3.1.0
gunicorn==23.0.0
google-auth==2.38.0
google-auth-oauthlib==1.2.1
google-api-python-client==2.166.0
google-cloud-firestore==2.20.2
requests==2.32.3
python-dotenv==1.1.0
Werkzeug==3.1.3
openpyxl==3.1.5
```

### 19.4 파일 구조

```
app.py                      # Flask 앱, 보안 설정, Firestore 세션 자동 복원
routes/
  auth.py                   # Google OAuth, 데코레이터
  main.py                   # 목록 화면
  item.py                   # 등록/수정/삭제/AJAX 엔드포인트
  sheet.py                  # 시트 연결/가져오기/CSV 업로드
  settings.py               # 설정 화면
services/
  google_sheets.py          # Sheets API 래퍼 (CRUD, 배치 저장, 삭제 이관)
  firestore_session.py      # Firestore refresh_token 세션 저장/갱신/삭제
  tmdb.py                   # TMDb 검색, 동기/비동기 보강
  tmdb_tracker.py           # 비동기 TMDb 진행 상태 추적
  csv_import.py             # CSV/Excel 파싱, 날짜·평점 변환
templates/
  list.html                 # 목록 메인
  partials/item_form.html   # 등록/수정 공통 폼
  connect.html              # 시트 연결
  import_sheet.html         # 시트 가져오기
  upload_csv.html           # CSV 가져오기
  settings.html             # 설정
static/
  css/style.css
  js/main.js
Dockerfile                  # Cloud Run 컨테이너 이미지
scripts/deploy.sh           # Cloud Run 배포 스크립트
version.py                  # 앱 버전
```

### 19.5 런타임 설정

- 포트: 8090
- 실행: `export $(cat .env | xargs) && python3 app.py`
- Cloud Run 실행: `gunicorn --bind "0.0.0.0:${PORT}" --workers 2 --threads 8 --timeout 60 app:app`
- 필수 환경 변수: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `FLASK_SECRET_KEY`, `REDIRECT_URI`
- 선택 환경 변수: `TMDB_API_KEY` (미설정 시 TMDb 기능 전체 스킵)
- 배포 선택 환경 변수: `GOOGLE_CLOUD_PROJECT`, `CLOUD_RUN_REGION`
- 환경 구분: `APP_ENV=development|production`

---

## 20. 완료 기준

| 기능 | 상태 |
|------|------|
| Google 로그인 | ✅ |
| Google Sheet 신규 생성 / URL 연결 | ✅ |
| 목록 조회 | ✅ |
| 제목 / 전체 검색 (디바운스) | ✅ |
| 검색·필터 후 검색창 포커스 유지 | ✅ |
| category / 관람 여부 필터 | ✅ |
| 8가지 정렬 기준 | ✅ |
| 등록 (TMDb 자동 연결 포함) | ✅ |
| 수정 모달 (원제·링크·평점 포함) | ✅ |
| 수정 모달 TMDb 업데이트 버튼 | ✅ |
| 삭제 (삭제 워크시트 이관) | ✅ |
| 삭제된 항목 조회 및 복구 | ✅ |
| 카드 클릭 후기/요약 펼침 | ✅ |
| 관람 여부 토글 (AJAX) | ✅ |
| 카드 내 🔗 아이콘으로 TMDb 링크 표시 | ✅ |
| 타 Google Sheet 가져오기 (중복 건너뜀) | ✅ |
| CSV 가져오기 (문자 평점·날짜 변환, 50건 미리보기) | ✅ |
| Excel(.xlsx/.xls) 가져오기 | ✅ |
| CSV "보고 싶어요" 항목 정상 가져오기 | ✅ |
| 배치 저장 (단일 API 호출) | ✅ |
| 비동기 TMDb 보강 (가져오기 후 백그라운드) | ✅ |
| TMDb 진행 상태 아이콘 실시간 표시 | ✅ |
| 진행률 % 배너 | ✅ |
| 원제(originalTitle) 수집 및 표시 | ✅ |
| 설정 (문서명·워크시트명 변경, 기본 정렬) | ✅ |
| Firestore refresh_token 영구 세션 복원 | ✅ |
| CSRF 및 세션 쿠키 보안 설정 | ✅ |
| 수정 충돌 방지(optimistic locking) | ✅ |
| Cloud Run 배포 구성 | ✅ |
| 헤더 버전·사용자명 표시 | ✅ |
