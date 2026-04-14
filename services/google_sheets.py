import re
import uuid
from datetime import datetime
from googleapiclient.discovery import build

WORKSHEET_NAME = "My Favorite Watch"
DELETED_WORKSHEET_NAME = "삭제"

HEADERS = [
    "id", "title", "titleLink", "genre", "category",
    "watched", "rating", "officialRating", "watchedAt",
    "registeredAt", "updatedAt", "review", "synopsis",
]

DELETED_HEADERS = HEADERS + ["deletedAt"]


def _sheets_service(credentials):
    return build("sheets", "v4", credentials=credentials)


def extract_sheet_id(url: str) -> str | None:
    """Google Sheet URL에서 sheetId를 추출."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def ensure_worksheet(credentials, sheet_id: str, worksheet_name: str, headers: list) -> str:
    """워크시트가 없으면 생성하고 헤더를 추가. 워크시트 GID 반환."""
    service = _sheets_service(credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = spreadsheet.get("sheets", [])

    existing = next(
        (s for s in sheets if s["properties"]["title"] == worksheet_name), None
    )
    if existing:
        return str(existing["properties"]["sheetId"])

    # 워크시트 생성
    body = {"requests": [{"addSheet": {"properties": {"title": worksheet_name}}}]}
    response = service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    new_sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]

    # 헤더 추가
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()

    return str(new_sheet_id)


def verify_sheet_access(credentials, sheet_id: str) -> dict:
    """시트 접근 가능 여부 확인. 성공 시 시트 제목 반환."""
    service = _sheets_service(credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return {"title": spreadsheet["properties"]["title"]}


def get_all_items(credentials, sheet_id: str) -> list[dict]:
    """My Favorite Watch 워크시트에서 모든 작품 조회."""
    service = _sheets_service(credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return []

    header = rows[0]
    items = []
    for row in rows[1:]:
        # 빈 컬럼 채우기
        padded = row + [""] * (len(header) - len(row))
        item = dict(zip(header, padded))
        items.append(item)
    return items


def _find_row_index(credentials, sheet_id: str, item_id: str) -> int | None:
    """id로 행 인덱스(1-based, 헤더 제외) 반환. 없으면 None."""
    service = _sheets_service(credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'!A:A",
    ).execute()
    rows = result.get("values", [])
    for i, row in enumerate(rows):
        if i == 0:
            continue  # 헤더 스킵
        if row and row[0] == item_id:
            return i + 1  # 1-based row number
    return None


def append_item(credentials, sheet_id: str, data: dict) -> dict:
    """새 작품 등록."""
    service = _sheets_service(credentials)
    now = datetime.utcnow().isoformat()
    item_id = str(uuid.uuid4())

    row = [
        item_id,
        data.get("title", ""),
        data.get("titleLink", ""),
        data.get("genre", ""),
        data.get("category", ""),
        "true" if data.get("watched") else "false",
        str(data.get("rating", "")),
        str(data.get("officialRating", "")),
        data.get("watchedAt", ""),
        now,  # registeredAt
        now,  # updatedAt
        data.get("review", ""),
        data.get("synopsis", ""),
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    return dict(zip(HEADERS, row))


def update_item(credentials, sheet_id: str, item_id: str, data: dict) -> dict | None:
    """기존 작품 수정."""
    row_index = _find_row_index(credentials, sheet_id, item_id)
    if row_index is None:
        return None

    service = _sheets_service(credentials)
    now = datetime.utcnow().isoformat()

    # 기존 데이터 조회
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'!A{row_index}:{chr(64+len(HEADERS))}{row_index}",
    ).execute()
    existing_row = result.get("values", [[]])[0]
    existing = dict(zip(HEADERS, existing_row + [""] * (len(HEADERS) - len(existing_row))))

    row = [
        item_id,
        data.get("title", existing.get("title", "")),
        data.get("titleLink", existing.get("titleLink", "")),
        data.get("genre", existing.get("genre", "")),
        data.get("category", existing.get("category", "")),
        "true" if data.get("watched") else "false",
        str(data.get("rating", existing.get("rating", ""))),
        str(data.get("officialRating", existing.get("officialRating", ""))),
        data.get("watchedAt", existing.get("watchedAt", "")),
        existing.get("registeredAt", now),
        now,  # updatedAt
        data.get("review", existing.get("review", "")),
        data.get("synopsis", existing.get("synopsis", "")),
    ]

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'!A{row_index}",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()

    return dict(zip(HEADERS, row))


def delete_item(credentials, sheet_id: str, item_id: str) -> bool:
    """작품 삭제 후 '삭제' 워크시트로 이관."""
    row_index = _find_row_index(credentials, sheet_id, item_id)
    if row_index is None:
        return False

    service = _sheets_service(credentials)

    # 삭제 전 데이터 읽기
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{WORKSHEET_NAME}'!A{row_index}:{chr(64+len(HEADERS))}{row_index}",
    ).execute()
    row_data = result.get("values", [[]])[0]

    # '삭제' 워크시트 확보
    ensure_worksheet(credentials, sheet_id, DELETED_WORKSHEET_NAME, DELETED_HEADERS)

    # 삭제 시트에 이관
    deleted_row = row_data + [""] * (len(HEADERS) - len(row_data))
    deleted_row.append(datetime.utcnow().isoformat())
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{DELETED_WORKSHEET_NAME}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [deleted_row]},
    ).execute()

    # 원본 시트에서 행 삭제
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = spreadsheet.get("sheets", [])
    main_sheet = next(
        (s for s in sheets if s["properties"]["title"] == WORKSHEET_NAME), None
    )
    if main_sheet is None:
        return False

    gid = main_sheet["properties"]["sheetId"]
    body = {
        "requests": [{
            "deleteDimension": {
                "range": {
                    "sheetId": gid,
                    "dimension": "ROWS",
                    "startIndex": row_index - 1,
                    "endIndex": row_index,
                }
            }
        }]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    return True


def update_watched(credentials, sheet_id: str, item_id: str, watched: bool) -> bool:
    """관람 여부만 빠르게 업데이트."""
    row_index = _find_row_index(credentials, sheet_id, item_id)
    if row_index is None:
        return False

    service = _sheets_service(credentials)
    watched_col = chr(64 + HEADERS.index("watched") + 1)
    updated_col = chr(64 + HEADERS.index("updatedAt") + 1)

    now = datetime.utcnow().isoformat()
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {
                    "range": f"'{WORKSHEET_NAME}'!{watched_col}{row_index}",
                    "values": [["true" if watched else "false"]],
                },
                {
                    "range": f"'{WORKSHEET_NAME}'!{updated_col}{row_index}",
                    "values": [[now]],
                },
            ],
        },
    ).execute()
    return True
