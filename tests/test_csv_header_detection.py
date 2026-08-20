"""CSV/Excel 헤더 판정 회귀 테스트.

업로드 안내(templates/upload_csv.html)는 컬럼 순서를 "관람여부, 장르, 제목, ..."
로 안내한다. 안내대로 "관람여부" 헤더를 넣은 CSV 파일을 올리면, 수정 전에는
헤더 행이 제목 "제목"인 가짜 작품으로 등록되었다 (parse_csv 가 "관람"/"watched"/
빈칸만 헤더로 인식했기 때문). Excel 경로는 "관람여부"를 이미 인식해 같은 파일이
확장자에 따라 다르게 처리되는 불일치도 있었다.
"""

import io

import openpyxl

from services.csv_import import is_header_row, parse_csv, parse_xlsx


def test_is_header_row_recognizes_all_known_variants():
    assert is_header_row("관람")
    assert is_header_row("관람여부")
    assert is_header_row("watched")
    assert is_header_row("")
    assert is_header_row("  관람여부  ")  # 공백 허용
    assert not is_header_row("v")
    assert not is_header_row("영화 제목")


def test_parse_csv_skips_gwanlamyeobu_header_row():
    content = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,액션,진짜 작품,A,2026.01.01,2026.01.02,좋았다\n"
    ).encode("utf-8")
    items = parse_csv(content)
    assert len(items) == 1
    assert items[0]["title"] == "진짜 작품"


def test_parse_csv_without_header_variant_still_works():
    # 헤더가 "관람"만 있는 기존 케이스도 계속 정상 동작해야 한다.
    content = (
        "관람,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,드라마,다른 작품,B,2026.02.01,2026.02.02,보통\n"
    ).encode("utf-8")
    items = parse_csv(content)
    assert len(items) == 1
    assert items[0]["title"] == "다른 작품"


def _build_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_xlsx_skips_gwanlamyeobu_header_row():
    content = _build_xlsx([
        ["관람여부", "장르", "제목", "평점", "등록날짜", "관람날짜", "간단후기"],
        ["v", "액션", "엑셀 작품", "A", "2026.01.01", "2026.01.02", "좋았다"],
    ])
    items = parse_xlsx(content)
    assert len(items) == 1
    assert items[0]["title"] == "엑셀 작품"


def test_csv_and_xlsx_agree_on_same_header_variant():
    """같은 헤더 문구를 쓴 CSV와 Excel 파일이 같은 결과를 내야 한다."""
    csv_content = (
        "관람여부,장르,제목,평점,등록날짜,관람날짜,간단후기\n"
        "v,SF,공통 작품,A,2026.01.01,2026.01.02,좋음\n"
    ).encode("utf-8")
    xlsx_content = _build_xlsx([
        ["관람여부", "장르", "제목", "평점", "등록날짜", "관람날짜", "간단후기"],
        ["v", "SF", "공통 작품", "A", "2026.01.01", "2026.01.02", "좋음"],
    ])

    csv_items = parse_csv(csv_content)
    xlsx_items = parse_xlsx(xlsx_content)

    assert len(csv_items) == len(xlsx_items) == 1
    assert csv_items[0]["title"] == xlsx_items[0]["title"] == "공통 작품"
