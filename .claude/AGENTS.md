# My Favorite Watch - Local Agents

이 파일은 My Favorite Watch 프로젝트 전용 agent 보완 지침입니다. 전역 agent는 `@../agent-hub/.claude/AGENTS.md`를 따른다.

## @watch-tracker

- 역할: 시청 데이터 정합성 관리
- 책임: Google Sheets 연동, CSV 가져오기, 중복 처리, 삭제 워크시트 이관, 정렬/필터 결과 검증
- 트리거: 데이터 모델, 목록 조회, 등록/수정/삭제, 가져오기 흐름 변경 시

## @tmdb-validator

- 역할: TMDb 연동 검증
- 책임: 제목 검색 우선순위, 공식 링크/평점/원제 갱신, 실패 상태 처리 검증
- 트리거: TMDb API 호출, 배치 검색, 작품 링크/평점 표시 변경 시
