#!/bin/bash
# 남은 커밋 4개를 순서대로 실행
# 사용법: bash scripts/commit_all.sh

set -e
cd "$(git rev-parse --show-toplevel)"

# stale lock 파일 제거
rm -f .git/index.lock .git/HEAD.lock

echo "=== Commit 2: 삭제 항목 복구 ==="
git add services/google_sheets.py routes/item.py routes/main.py templates/list.html
git commit -m "feat: 삭제된 항목 복구 기능 추가 (item 7)

- google_sheets: get_deleted_items(), restore_item(), get_item_by_id() 추가
- routes/item: POST /item/<id>/restore 엔드포인트 추가
- routes/main: tab=active/deleted 파라미터로 삭제 탭 분기
- templates/list: 탭 UI(작품 목록/삭제된 항목) 및 복구 버튼 추가"

echo "=== Commit 3: 페이지네이션 ==="
git add routes/main.py templates/list.html
git commit -m "feat: 페이지네이션 추가 (item 8)

- routes/main: PAGE_SIZE=50, offset 파라미터 기반 슬라이싱
- templates/list: 이전/다음 페이지 네비게이션 UI 추가"

echo "=== Commit 4: Optimistic locking ==="
git add routes/item.py services/google_sheets.py templates/list.html static/js/main.js
git commit -m "feat: Optimistic locking으로 동시 편집 충돌 감지 (item 9)

- google_sheets: get_item_by_id() 추가
- routes/item: 수정 시 original_updated_at vs 현재 updatedAt 비교
- templates/list: 수정 폼에 original_updated_at hidden 필드 추가
- main.js: openEditModal에서 updatedAt 세팅"

echo "=== Commit 5: Excel 가져오기 ==="
git add requirements.txt services/csv_import.py routes/sheet.py templates/upload_csv.html
git commit -m "feat: Excel(.xlsx) 파일 가져오기 지원 (item 10)

- requirements: openpyxl 추가
- csv_import: parse_xlsx() 함수 추가
- routes/sheet: xlsx 확장자 감지 후 parse_xlsx 호출
- templates/upload_csv: 파일 accept에 .xlsx/.xls 추가"

echo ""
echo "✅ 커밋 완료. 현재 로그:"
git log --oneline -6
