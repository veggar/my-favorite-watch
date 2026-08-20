"""가져오기 실행 전 영향 범위 계산 (P2-4).

CSV/Excel 업로드와 다른 시트 가져오기는 모두 "제목이 이미 있으면 건너뛴다"는
동일한 규칙을 쓴다. 그동안 이 결과는 **가져오기를 실행한 뒤에야** 알 수 있었기
때문에, 사용자는 몇 건이 실제로 추가되는지 모른 채 제출해야 했다.

이 모듈은 그 규칙을 순수 함수로 분리해, 제출 전 미리보기 단계에서도 같은 수치를
계산할 수 있게 한다. 규칙이 한 곳에만 있으므로 미리보기와 실제 결과가 어긋나지
않는다.

중복 판정 규칙 (services/google_sheets.import_from_sheet, routes/sheet.upload_csv 와 동일):
- 제목을 `strip().lower()` 한 값으로 비교한다.
- 제목이 비어 있으면 중복 검사를 하지 않고 그대로 추가한다.
- **파일/시트 안에서의 중복은 건너뛰지 않는다.** 기존 시트에 없는 제목이라면 같은
  제목이 두 번 있어도 두 건 모두 추가된다. 사용자가 의도치 않게 중복 행을 만들 수
  있으므로 경고용으로 따로 집계한다.
"""

from __future__ import annotations


def normalize_title(title: str) -> str:
    """중복 비교용 제목 정규화."""
    return (title or "").strip().lower()


def plan_import(items: list[dict], existing_title_map: dict | None) -> dict:
    """가져오기 결과를 미리 계산한다.

    Args:
        items: 가져올 항목 목록. 각 항목은 `title` 키를 가진다.
        existing_title_map: 대상 시트의 `정규화 제목 -> item` 매핑.
            `None` 이면 대상 시트를 조회하지 못한 것으로 보고 중복 계산을 생략한다.

    Returns:
        total, to_add, duplicates, duplicate_titles, in_file_duplicate_titles,
        untitled, checked 를 담은 dict.
    """
    total = len(items)

    if existing_title_map is None:
        # 대상 시트를 읽지 못한 경우. 실제 추가 건수를 단정하지 않는다.
        return {
            "total": total,
            "to_add": total,
            "duplicates": 0,
            "duplicate_titles": [],
            "in_file_duplicate_titles": [],
            "untitled": sum(1 for it in items if not normalize_title(it.get("title", ""))),
            "checked": False,
        }

    duplicate_titles: list[str] = []
    in_file_duplicate_titles: list[str] = []
    seen_new: set[str] = set()
    seen_dup: set[str] = set()
    duplicates = 0
    untitled = 0

    for item in items:
        raw_title = (item.get("title") or "").strip()
        key = normalize_title(raw_title)

        if not key:
            untitled += 1
            continue

        if key in existing_title_map:
            duplicates += 1
            if key not in seen_dup:
                seen_dup.add(key)
                duplicate_titles.append(raw_title)
            continue

        if key in seen_new:
            # 기존 시트에는 없지만 이번 가져오기 안에서 중복된 제목.
            # 현재 규칙상 건너뛰지 않고 모두 추가되므로 경고로만 표시한다.
            if raw_title not in in_file_duplicate_titles:
                in_file_duplicate_titles.append(raw_title)
        else:
            seen_new.add(key)

    return {
        "total": total,
        "to_add": total - duplicates,
        "duplicates": duplicates,
        "duplicate_titles": duplicate_titles,
        "in_file_duplicate_titles": in_file_duplicate_titles,
        "untitled": untitled,
        "checked": True,
    }
