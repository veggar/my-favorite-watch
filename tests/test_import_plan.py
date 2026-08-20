"""services.import_plan.plan_import 단위 테스트 (P2-4)."""

from services.import_plan import normalize_title, plan_import


def test_normalize_title_strips_and_lowercases():
    assert normalize_title("  Some Title  ") == "some title"
    assert normalize_title("") == ""
    assert normalize_title(None) == ""


def test_plan_import_checked_false_when_existing_map_unavailable():
    items = [{"title": "A"}, {"title": "B"}]
    plan = plan_import(items, None)
    assert plan["checked"] is False
    assert plan["total"] == 2
    # 대상 시트를 읽지 못했으므로 추가 건수를 단정하지 않고 전체를 그대로 반환한다.
    assert plan["to_add"] == 2
    assert plan["duplicates"] == 0


def test_plan_import_counts_duplicates_against_existing_sheet():
    items = [{"title": "Already Here"}, {"title": "New One"}]
    existing = {"already here": {"title": "Already Here"}}
    plan = plan_import(items, existing)
    assert plan["checked"] is True
    assert plan["total"] == 2
    assert plan["to_add"] == 1
    assert plan["duplicates"] == 1
    assert plan["duplicate_titles"] == ["Already Here"]


def test_plan_import_untitled_rows_are_not_duplicate_checked():
    items = [{"title": ""}, {"title": "  "}, {"title": "Real Title"}]
    plan = plan_import(items, {})
    assert plan["untitled"] == 2
    assert plan["to_add"] == 3  # 제목 없는 행도 그대로 추가 대상에 포함된다
    assert plan["duplicates"] == 0


def test_plan_import_in_file_duplicates_are_flagged_but_not_deduped():
    # 기존 시트에는 없지만 파일 내에서 같은 제목이 반복되는 경우.
    # 현재 규칙상 두 건 모두 추가되므로 to_add 에서 빼지 않고 경고만 남긴다.
    # 경고 표시용 목록은 정규화 전 원문 기준으로 쌓이므로, 대소문자가 다른
    # 표기는 각각 별도 항목으로 나열된다.
    items = [{"title": "Repeat"}, {"title": "Repeat"}, {"title": "repeat"}]
    plan = plan_import(items, {})
    assert plan["to_add"] == 3
    assert plan["duplicates"] == 0
    assert plan["in_file_duplicate_titles"] == ["Repeat", "repeat"]


def test_plan_import_empty_items():
    plan = plan_import([], {})
    assert plan["total"] == 0
    assert plan["to_add"] == 0
    assert plan["checked"] is True
