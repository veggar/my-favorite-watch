import csv
import uuid
import re
import io
from datetime import datetime

# 문자 등급 → 숫자 평점 매핑
GRADE_MAP = {
    "a++": 5.0, "a+": 5.0,
    "a":   4.5, "a-": 4.0,
    "b++": 4.0, "b+": 4.0,
    "b0":  3.5, "b":  3.5, "b?": 3.5,
    "b--": 3.0, "b-": 3.0,
    "c++": 3.0, "c+": 2.5,
    "c":   2.0, "c-": 1.5,
    "d":   1.0,
}

# 카테고리 키워드 매핑 (장르 컬럼 값 → category)
CATEGORY_KEYWORDS = {
    "애니": "애니",
    "드라마": "드라마",
    "다큐": "다큐",
    "다형": "다큐",
    "역사": "다큐",
    "교육": "다큐",
    "sf/코믹": "영화",
    "코믹": "영화",
    "영화": "영화",
}


def _parse_grade(raw: str) -> str:
    """문자 등급을 숫자 평점(0.0~5.0)으로 변환. 변환 불가 시 빈 문자열."""
    if not raw:
        return ""
    cleaned = raw.strip().lower().split()[0]  # "B+ ..." → "b+"
    # 괄호나 숫자 등 제거
    cleaned = re.sub(r"[^a-z+\-?0]", "", cleaned)
    return str(GRADE_MAP[cleaned]) if cleaned in GRADE_MAP else ""


def _parse_date(raw: str) -> str:
    """다양한 날짜 형식을 ISO(YYYY-MM-DD) 문자열로 변환. 파싱 불가 시 빈 문자열."""
    if not raw:
        return ""
    # 공백 제거 후 숫자만 추출
    cleaned = raw.strip()
    # "2020.01.03" / "2020. 01. 03" / "2020.01.x" 등 처리
    parts = re.split(r"[\.\-/\s]+", cleaned)
    parts = [p.strip() for p in parts if p.strip()]
    # 숫자 아닌 부분 제거 (예: "x", "?")
    numeric_parts = [p for p in parts if re.fullmatch(r"\d+", p)]

    if len(numeric_parts) >= 3:
        y, m, d = numeric_parts[0], numeric_parts[1].zfill(2), numeric_parts[2].zfill(2)
        # 유효성 확인
        try:
            datetime.strptime(f"{y}-{m}-{d}", "%Y-%m-%d")
            return f"{y}-{m}-{d}"
        except ValueError:
            pass
    if len(numeric_parts) == 2:
        y, m = numeric_parts[0], numeric_parts[1].zfill(2)
        return f"{y}-{m}-01"
    if len(numeric_parts) == 1 and len(numeric_parts[0]) == 4:
        return f"{numeric_parts[0]}-01-01"
    return ""


def _infer_category(genre_raw: str) -> tuple[str, str]:
    """
    장르 컬럼 값에서 (category, genre) 튜플 반환.
    알려진 카테고리 키워드면 category로, 그 외는 genre로.
    """
    if not genre_raw:
        return "영화", ""
    lower = genre_raw.strip().lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in lower:
            return cat, ""
    # 알 수 없는 값은 genre에 보존
    return "기타", genre_raw.strip()


def parse_csv(file_content: bytes, encoding: str = "utf-8") -> list[dict]:
    """
    CSV 바이트를 파싱하여 앱 데이터 구조 목록으로 반환.
    첫 행은 헤더로 간주하고 건너뜀.
    제목이 없는 행은 건너뜀.
    """
    # 인코딩 자동 감지 시도
    for enc in [encoding, "utf-8-sig", "cp949", "euc-kr"]:
        try:
            text = file_content.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        raise ValueError("파일 인코딩을 인식할 수 없습니다. UTF-8 또는 EUC-KR 파일을 사용해주세요.")

    now = datetime.utcnow().isoformat()
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    # 첫 행 헤더 확인 (한글 헤더 or 데이터)
    start_idx = 0
    if rows and rows[0] and rows[0][0].strip() in ("관람", "watched", ""):
        start_idx = 1  # 헤더 스킵

    items = []
    for row in rows[start_idx:]:
        # 충분한 컬럼 확보
        padded = row + [""] * max(0, 7 - len(row))

        watched_raw = padded[0].strip().lower()
        genre_raw   = padded[1].strip()
        title       = padded[2].strip()
        rating_raw  = padded[3].strip()
        reg_raw     = padded[4].strip()
        watch_raw   = padded[5].strip()
        review      = padded[6].strip()

        # 제목 없으면 스킵
        if not title:
            continue

        watched = watched_raw in ("v", "✓", "true", "y", "yes", "o")
        category, genre = _infer_category(genre_raw)
        rating = _parse_grade(rating_raw)
        registered_at = _parse_date(reg_raw) or now
        watched_at = _parse_date(watch_raw) if watched else ""

        items.append({
            "id":           str(uuid.uuid4()),
            "title":        title,
            "titleLink":    "",
            "genre":        genre,
            "category":     category,
            "watched":      "true" if watched else "false",
            "rating":       rating,
            "officialRating": "",
            "watchedAt":    watched_at,
            "registeredAt": registered_at,
            "updatedAt":    now,
            "review":       review,
            "synopsis":     "",
        })

    return items


def parse_xlsx(file_content: bytes) -> list[dict]:
    """
    Excel(.xlsx/.xls) 바이트를 파싱하여 앱 데이터 구조 목록으로 반환.
    CSV와 동일한 컬럼 순서를 기대: 관람여부, 장르, 제목, 평점, 등록날짜, 관람날짜, 간단후기
    """
    import io
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
    ws = wb.active

    now = datetime.utcnow().isoformat()
    items = []
    first_row = True

    for row in ws.iter_rows(values_only=True):
        # 첫 행이 헤더인지 확인
        if first_row:
            first_row = False
            first_val = str(row[0] or "").strip().lower()
            if first_val in ("관람", "watched", "관람여부", ""):
                continue  # 헤더 스킵

        padded = [str(cell) if cell is not None else "" for cell in row]
        padded += [""] * max(0, 7 - len(padded))

        watched_raw = padded[0].strip().lower()
        genre_raw   = padded[1].strip()
        title       = padded[2].strip()
        rating_raw  = padded[3].strip()
        reg_raw     = padded[4].strip()
        watch_raw   = padded[5].strip()
        review      = padded[6].strip()

        if not title:
            continue

        watched = watched_raw in ("v", "✓", "true", "y", "yes", "o")
        category, genre = _infer_category(genre_raw)
        rating = _parse_grade(rating_raw)
        registered_at = _parse_date(reg_raw) or now
        watched_at = _parse_date(watch_raw) if watched else ""

        items.append({
            "id":           str(uuid.uuid4()),
            "title":        title,
            "titleLink":    "",
            "genre":        genre,
            "category":     category,
            "watched":      "true" if watched else "false",
            "rating":       rating,
            "officialRating": "",
            "watchedAt":    watched_at,
            "registeredAt": registered_at,
            "updatedAt":    now,
            "review":       review,
            "synopsis":     "",
        })

    wb.close()
    return items


def summarize(items: list[dict]) -> dict:
    """파싱 결과 요약 통계."""
    watched = sum(1 for it in items if it["watched"] == "true")
    return {
        "total":   len(items),
        "watched": watched,
        "want":    len(items) - watched,
        "categories": _count(items, "category"),
    }


def _count(items, key):
    result = {}
    for it in items:
        v = it.get(key, "") or "미분류"
        result[v] = result.get(v, 0) + 1
    return result
