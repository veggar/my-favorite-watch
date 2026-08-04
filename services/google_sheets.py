import re
import uuid
from datetime import datetime
from googleapiclient.discovery import build

DEFAULT_WORKSHEET_NAME = "My Favorite Watch"
DEFAULT_SPREADSHEET_NAME = "My Favorite Watch"
DELETED_WORKSHEET_NAME = "삭제"

HEADERS = [
    "id", "title", "titleLink", "originalTitle", "genre", "category",
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


def find_spreadsheet_by_name(credentials, name: str = DEFAULT_SPREADSHEET_NAME) -> dict | None:
    """Google Drive에서 지정한 이름의 스프레드시트를 검색한다.

    검색만 수행하며 연결은 하지 않는다. 찾지 못하면 None을 반환한다.
    """
    drive = build("drive", "v3", credentials=credentials)
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"name='{escaped}'"
        " and mimeType='application/vnd.google-apps.spreadsheet'"
        " and trashed=false"
    )
    result = drive.files().list(
        q=query, fields="files(id,name)", pageSize=1
    ).execute()
    files = result.get("files", [])
    if not files:
        return None
    return {"sheet_id": files[0]["id"], "title": files[0].get("name", name)}


def create_spreadsheet(credentials, doc_title: str, worksheet_name: str) -> dict:
    """새 구글 시트 문서를 생성하고 워크시트를 초기화. sheet_id와 sheet_url 반환."""
    service = _sheets_service(credentials)
    body = {
        "properties": {"title": doc_title},
        "sheets": [{"properties": {"title": worksheet_name}}],
    }
    spreadsheet = service.spreadsheets().create(body=body).execute()
    sheet_id = spreadsheet["spreadsheetId"]

    # 헤더 추가
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()

    # 삭제 워크시트도 생성
    ensure_worksheet(credentials, sheet_id, DELETED_WORKSHEET_NAME, DELETED_HEADERS)

    return {
        "sheet_id": sheet_id,
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}",
    }


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

    body = {"requests": [{"addSheet": {"properties": {"title": worksheet_name}}}]}
    response = service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    new_sheet_id = response["replies"][0]["addSheet"]["properties"]["sheetId"]

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()

    return str(new_sheet_id)


def verify_sheet_access(credentials, sheet_id: str) -> dict:
    """시트 접근 가능 여부 확인. 성공 시 문서 제목과 워크시트 목록 반환."""
    service = _sheets_service(credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    worksheets = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
    return {
        "title": spreadsheet["properties"]["title"],
        "worksheets": worksheets,
    }


def import_from_sheet(credentials, src_sheet_id: str, src_worksheet: str,
                      dst_sheet_id: str, dst_worksheet: str,
                      existing_title_map: dict | None = None) -> int:
    """다른 구글 시트의 워크시트 데이터를 현재 시트로 가져오기. 가져온 행 수 반환."""
    service = _sheets_service(credentials)

    # 소스 데이터 읽기
    result = service.spreadsheets().values().get(
        spreadsheetId=src_sheet_id,
        range=f"'{src_worksheet}'",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return 0

    src_header = rows[0]
    data_rows = rows[1:]

    # 대상 워크시트의 현재 헤더 확인
    dst_result = service.spreadsheets().values().get(
        spreadsheetId=dst_sheet_id,
        range=f"'{dst_worksheet}'!1:1",
    ).execute()
    dst_header = dst_result.get("values", [[]])[0] or HEADERS

    # 소스 컬럼 → 대상 컬럼 매핑
    imported = 0
    now = datetime.utcnow().isoformat()
    rows_to_append = []

    for src_row in data_rows:
        src_data = dict(zip(src_header, src_row + [""] * (len(src_header) - len(src_row))))

        # 중복 제목 건너뛰기
        if existing_title_map is not None:
            title_key = src_data.get("title", "").strip().lower()
            if title_key and title_key in existing_title_map:
                continue

        # id가 없으면 새로 생성
        if not src_data.get("id"):
            src_data["id"] = str(uuid.uuid4())
        if not src_data.get("registeredAt"):
            src_data["registeredAt"] = now
        if not src_data.get("updatedAt"):
            src_data["updatedAt"] = now

        dst_row = [src_data.get(col, "") for col in dst_header]
        rows_to_append.append(dst_row)
        imported += 1

    if rows_to_append:
        service.spreadsheets().values().append(
            spreadsheetId=dst_sheet_id,
            range=f"'{dst_worksheet}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows_to_append},
        ).execute()

    return imported


def rename_spreadsheet(credentials, sheet_id: str, new_title: str) -> None:
    """구글 시트 문서 이름 변경."""
    service = _sheets_service(credentials)
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"updateSpreadsheetProperties": {
            "properties": {"title": new_title},
            "fields": "title",
        }}]},
    ).execute()


def rename_worksheet(credentials, sheet_id: str, old_name: str, new_name: str) -> None:
    """워크시트(탭) 이름 변경."""
    service = _sheets_service(credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = spreadsheet.get("sheets", [])
    target = next((s for s in sheets if s["properties"]["title"] == old_name), None)
    if target is None:
        raise ValueError(f"워크시트 '{old_name}'를 찾을 수 없습니다.")

    gid = target["properties"]["sheetId"]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": gid, "title": new_name},
            "fields": "title",
        }}]},
    ).execute()


def get_all_items(credentials, sheet_id: str, worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> list[dict]:
    """워크시트에서 모든 작품 조회."""
    service = _sheets_service(credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        return []

    header = rows[0]
    items = []
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        item = dict(zip(header, padded))
        items.append(item)
    return items


def get_deleted_items(credentials, sheet_id: str) -> list[dict]:
    """'삭제' 워크시트에서 삭제된 항목 목록 조회."""
    service = _sheets_service(credentials)
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{DELETED_WORKSHEET_NAME}'",
        ).execute()
    except Exception:
        return []
    rows = result.get("values", [])
    if len(rows) < 2:
        return []

    header = rows[0]
    items = []
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        item = dict(zip(header, padded))
        items.append(item)
    return items


def get_item_by_id(credentials, sheet_id: str, item_id: str,
                   worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> dict | None:
    """ID로 단일 항목 조회 (optimistic locking 비교용)."""
    items = get_all_items(credentials, sheet_id, worksheet_name)
    return next((it for it in items if it.get("id") == item_id), None)


def get_items_title_map(credentials, sheet_id: str,
                        worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> dict[str, dict]:
    """제목(소문자) → item dict 매핑 반환. 중복 감지용."""
    items = get_all_items(credentials, sheet_id, worksheet_name)
    return {it.get("title", "").strip().lower(): it for it in items if it.get("title")}


def append_items_batch(credentials, sheet_id: str, items: list[dict],
                       worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> list[str]:
    """여러 항목을 한 번의 API 호출로 일괄 등록. 저장된 item_id 목록 반환."""
    if not items:
        return []
    service = _sheets_service(credentials)
    now = datetime.utcnow().isoformat()
    rows = []
    item_ids = []
    for data in items:
        item_id = data.get("id") or str(uuid.uuid4())
        item_ids.append(item_id)

        watched_val = data.get("watched", False)
        watched_str = "true" if (watched_val is True or str(watched_val).lower() == "true") else "false"

        row = [
            item_id,
            data.get("title", ""),
            data.get("titleLink", ""),
            data.get("originalTitle", ""),
            data.get("genre", ""),
            data.get("category", ""),
            watched_str,
            str(data.get("rating", "")),
            str(data.get("officialRating", "")),
            data.get("watchedAt", "") if watched_str == "true" else "",
            data.get("registeredAt", now),
            now,
            data.get("review", ""),
            data.get("synopsis", ""),
        ]
        rows.append(row)

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return item_ids


def _find_row_index(credentials, sheet_id: str, item_id: str,
                    worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> int | None:
    """id로 행 인덱스(1-based) 반환. 없으면 None."""
    service = _sheets_service(credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A:A",
    ).execute()
    rows = result.get("values", [])
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if row and row[0] == item_id:
            return i + 1
    return None


def append_item(credentials, sheet_id: str, data: dict,
                worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> dict:
    """새 작품 등록."""
    service = _sheets_service(credentials)
    now = datetime.utcnow().isoformat()
    item_id = str(uuid.uuid4())

    watched_val = data.get("watched", False)
    watched_str = "true" if (watched_val is True or str(watched_val).lower() == "true") else "false"

    row = [
        item_id,
        data.get("title", ""),
        data.get("titleLink", ""),
        data.get("originalTitle", ""),
        data.get("genre", ""),
        data.get("category", ""),
        watched_str,
        str(data.get("rating", "")),
        str(data.get("officialRating", "")),
        data.get("watchedAt", "") if watched_str == "true" else "",
        now,
        now,
        data.get("review", ""),
        data.get("synopsis", ""),
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    return dict(zip(HEADERS, row))


def update_item(credentials, sheet_id: str, item_id: str, data: dict,
                worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> dict | None:
    """기존 작품 수정."""
    row_index = _find_row_index(credentials, sheet_id, item_id, worksheet_name)
    if row_index is None:
        return None

    service = _sheets_service(credentials)
    now = datetime.utcnow().isoformat()

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A{row_index}:{chr(64+len(HEADERS))}{row_index}",
    ).execute()
    existing_row = result.get("values", [[]])[0]
    existing = dict(zip(HEADERS, existing_row + [""] * (len(HEADERS) - len(existing_row))))

    watched_val = data.get("watched", existing.get("watched", False))
    watched_str = "true" if (watched_val is True or str(watched_val).lower() == "true") else "false"

    row = [
        item_id,
        data.get("title", existing.get("title", "")),
        data.get("titleLink", existing.get("titleLink", "")),
        data.get("originalTitle", existing.get("originalTitle", "")),
        data.get("genre", existing.get("genre", "")),
        data.get("category", existing.get("category", "")),
        watched_str,
        str(data.get("rating", existing.get("rating", ""))),
        str(data.get("officialRating", existing.get("officialRating", ""))),
        data.get("watchedAt", existing.get("watchedAt", "")) if watched_str == "true" else "",
        existing.get("registeredAt", now),
        now,
        data.get("review", existing.get("review", "")),
        data.get("synopsis", existing.get("synopsis", "")),
    ]

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A{row_index}",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()

    return dict(zip(HEADERS, row))


def delete_item(credentials, sheet_id: str, item_id: str,
                worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> bool:
    """작품 삭제 후 '삭제' 워크시트로 이관."""
    row_index = _find_row_index(credentials, sheet_id, item_id, worksheet_name)
    if row_index is None:
        return False

    service = _sheets_service(credentials)

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A{row_index}:{chr(64+len(HEADERS))}{row_index}",
    ).execute()
    row_data = result.get("values", [[]])[0]

    ensure_worksheet(credentials, sheet_id, DELETED_WORKSHEET_NAME, DELETED_HEADERS)

    deleted_row = row_data + [""] * (len(HEADERS) - len(row_data))
    deleted_row.append(datetime.utcnow().isoformat())
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{DELETED_WORKSHEET_NAME}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [deleted_row]},
    ).execute()

    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = spreadsheet.get("sheets", [])
    main_sheet = next(
        (s for s in sheets if s["properties"]["title"] == worksheet_name), None
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


def restore_item(credentials, sheet_id: str, item_id: str,
                 worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> bool:
    """'삭제' 워크시트의 항목을 원래 워크시트로 복구."""
    row_index = _find_row_index(credentials, sheet_id, item_id, DELETED_WORKSHEET_NAME)
    if row_index is None:
        return False

    service = _sheets_service(credentials)

    # 삭제 시트에서 데이터 읽기 (deletedAt 컬럼 제외)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{DELETED_WORKSHEET_NAME}'!A{row_index}:{chr(64+len(HEADERS))}{row_index}",
    ).execute()
    row_data = result.get("values", [[]])[0]

    # 원래 워크시트에 복구 (updatedAt 갱신)
    restored = row_data + [""] * (len(HEADERS) - len(row_data))
    restored[HEADERS.index("updatedAt")] = datetime.utcnow().isoformat()

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{worksheet_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [restored]},
    ).execute()

    # 삭제 시트에서 행 제거
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    deleted_sheet = next(
        (s for s in spreadsheet.get("sheets", [])
         if s["properties"]["title"] == DELETED_WORKSHEET_NAME),
        None,
    )
    if deleted_sheet:
        gid = deleted_sheet["properties"]["sheetId"]
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"deleteDimension": {"range": {
                "sheetId": gid, "dimension": "ROWS",
                "startIndex": row_index - 1, "endIndex": row_index,
            }}}]},
        ).execute()

    return True


def update_watched(credentials, sheet_id: str, item_id: str, watched: bool,
                   worksheet_name: str = DEFAULT_WORKSHEET_NAME) -> bool:
    """관람 여부만 빠르게 업데이트."""
    row_index = _find_row_index(credentials, sheet_id, item_id, worksheet_name)
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
                    "range": f"'{worksheet_name}'!{watched_col}{row_index}",
                    "values": [["true" if watched else "false"]],
                },
                {
                    "range": f"'{worksheet_name}'!{updated_col}{row_index}",
                    "values": [[now]],
                },
            ],
        },
    ).execute()
    return True
