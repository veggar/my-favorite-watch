import logging

from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from routes.auth import login_required, get_credentials
from services.errors import friendly_error, http_status
from services.google_sheets import (
    extract_sheet_id,
    verify_sheet_access,
    ensure_worksheet,
    create_spreadsheet,
    find_spreadsheet_by_name,
    import_from_sheet,
    get_all_items,
    get_items_title_map,
    append_items_batch,
    update_item,
    DEFAULT_SPREADSHEET_NAME,
    DEFAULT_WORKSHEET_NAME,
    HEADERS,
    DELETED_HEADERS,
    DELETED_WORKSHEET_NAME,
)
from services.tmdb import enrich_item, enrich_items_batch
from services.tmdb_tracker import mark_pending
from services.firestore_session import update_sheet_from_session

logger = logging.getLogger(__name__)

sheet_bp = Blueprint("sheet", __name__)


def _save_sheet_session(sheet_id: str, sheet_title: str, worksheet_name: str):
    session["sheet_id"] = sheet_id
    session["sheet_title"] = sheet_title
    session["worksheet_name"] = worksheet_name
    # 시트 설정은 기기가 아니라 사용자 단위로 저장한다(멀티 디바이스 공유).
    update_sheet_from_session(session.get("user_key", ""))


class ConnectError(Exception):
    """시트 연결 과정에서 사용자에게 그대로 보여줄 오류.

    메시지는 _friendly_sheet_error() 를 거쳐 이미 정제된 문구이므로
    화면에 노출해도 안전하다. 원본 예외는 `raise ... from e` 로 연결되며
    로그에만 남는다.
    """

    @property
    def user_message(self) -> str:
        return str(self)


def _friendly_sheet_error(e: Exception, prefix: str) -> str:
    """시트 관련 예외를 사용자용 문구로 변환한다. 원문은 로그로만 남는다."""
    status = http_status(e)
    if status == 403:
        logger.warning("시트 접근 권한 없음 (%s)", type(e).__name__)
        return "시트 접근 권한이 없습니다."
    if status == 404:
        logger.warning("시트를 찾을 수 없음 (%s)", type(e).__name__)
        return "시트를 찾을 수 없습니다."
    return friendly_error(e, prefix, context="sheet", log=logger)


def _attach_spreadsheet(sheet_id: str, worksheet_name: str, sheet_title: str = "") -> dict:
    """스프레드시트를 검증하고 필요한 워크시트를 준비한 뒤 세션에 저장한다."""
    credentials = get_credentials()
    worksheet_name = (worksheet_name or DEFAULT_WORKSHEET_NAME).strip() or DEFAULT_WORKSHEET_NAME
    try:
        info = verify_sheet_access(credentials, sheet_id)
        ensure_worksheet(credentials, sheet_id, worksheet_name, HEADERS)
        ensure_worksheet(credentials, sheet_id, DELETED_WORKSHEET_NAME, DELETED_HEADERS)
    except Exception as e:
        raise ConnectError(_friendly_sheet_error(e, "연결에 실패했습니다")) from e
    title = sheet_title or info["title"]
    _save_sheet_session(sheet_id, title, worksheet_name)
    return {"sheet_id": sheet_id, "title": title, "worksheet_name": worksheet_name}


def _connect_by_url(sheet_url: str, worksheet_name: str) -> dict:
    sheet_id = extract_sheet_id(sheet_url or "")
    if not sheet_id:
        raise ConnectError("올바른 Google Sheet URL을 입력해주세요.")
    return _attach_spreadsheet(sheet_id, worksheet_name)


def _create_new_spreadsheet(doc_title: str, worksheet_name: str) -> dict:
    doc_title = (doc_title or DEFAULT_SPREADSHEET_NAME).strip() or DEFAULT_SPREADSHEET_NAME
    worksheet_name = (worksheet_name or DEFAULT_WORKSHEET_NAME).strip() or DEFAULT_WORKSHEET_NAME
    credentials = get_credentials()
    try:
        result = create_spreadsheet(credentials, doc_title, worksheet_name)
    except Exception as e:
        raise ConnectError(_friendly_sheet_error(e, "시트 생성에 실패했습니다")) from e
    _save_sheet_session(result["sheet_id"], doc_title, worksheet_name)
    return {"sheet_id": result["sheet_id"], "title": doc_title, "worksheet_name": worksheet_name}


@sheet_bp.route("/connect", methods=["GET", "POST"])
@login_required
def connect():
    """시트 연결 화면.

    POST는 JavaScript를 사용할 수 없는 환경을 위한 폴백 경로이며,
    기본 플로우는 아래 JSON 엔드포인트를 사용한다.
    """
    error = None
    if request.method == "POST":
        action = request.form.get("action", "connect")
        try:
            if action == "create":
                _create_new_spreadsheet(
                    request.form.get("doc_title", ""),
                    request.form.get("worksheet_name", ""),
                )
            else:
                _connect_by_url(
                    request.form.get("sheet_url", "").strip(),
                    request.form.get("worksheet_name", ""),
                )
            return redirect(url_for("main.index"))
        except ConnectError as e:
            error = e.user_message

    return render_template("connect.html", user=session.get("user"), error=error,
                           default_worksheet=DEFAULT_WORKSHEET_NAME,
                           default_spreadsheet=DEFAULT_SPREADSHEET_NAME)


# ── 시트 연결 JSON 엔드포인트 ──────────────────────────────────────────────

@sheet_bp.route("/connect/discover", methods=["POST"])
@login_required
def connect_discover():
    """기본 이름의 시트를 검색만 한다. 연결은 사용자 확인 후 별도로 수행한다."""
    try:
        found = find_spreadsheet_by_name(get_credentials(), DEFAULT_SPREADSHEET_NAME)
    except Exception as e:
        return jsonify({"ok": False, "error": _friendly_sheet_error(e, "시트 검색에 실패했습니다")}), 502
    if not found:
        return jsonify({"ok": True, "found": False})
    return jsonify({"ok": True, "found": True, **found})


@sheet_bp.route("/connect/use-found", methods=["POST"])
@login_required
def connect_use_found():
    """검색된 시트를 사용자가 승인한 경우에만 연결한다."""
    data = request.get_json(silent=True) or {}
    sheet_id = (data.get("sheet_id") or "").strip()
    if not sheet_id:
        return jsonify({"ok": False, "error": "시트 ID가 누락되었습니다."}), 400
    try:
        info = _attach_spreadsheet(sheet_id, data.get("worksheet_name", ""), data.get("title", ""))
    except ConnectError as e:
        return jsonify({"ok": False, "error": e.user_message}), 400
    return jsonify({"ok": True, **info})


@sheet_bp.route("/connect/by-url", methods=["POST"])
@login_required
def connect_by_url():
    """사용자가 직접 입력한 URL로 연결한다."""
    data = request.get_json(silent=True) or {}
    try:
        info = _connect_by_url(data.get("sheet_url", ""), data.get("worksheet_name", ""))
    except ConnectError as e:
        return jsonify({"ok": False, "error": e.user_message}), 400
    return jsonify({"ok": True, **info})


@sheet_bp.route("/connect/create", methods=["POST"])
@login_required
def connect_create():
    """새 시트를 생성하고 연결한다."""
    data = request.get_json(silent=True) or {}
    try:
        info = _create_new_spreadsheet(data.get("doc_title", ""), data.get("worksheet_name", ""))
    except ConnectError as e:
        return jsonify({"ok": False, "error": e.user_message}), 400
    return jsonify({"ok": True, "created": True, **info})


@sheet_bp.route("/import-sheet", methods=["GET", "POST"])
@login_required
def import_sheet():
    """다른 구글 시트에서 데이터 가져오기."""
    error = None
    success = None
    worksheets = []
    src_sheet_id = ""

    if request.method == "POST":
        action = request.form.get("action", "preview")
        src_url = request.form.get("src_url", "").strip()
        src_sheet_id = extract_sheet_id(src_url) if src_url else request.form.get("src_sheet_id", "").strip()

        if not src_sheet_id:
            error = "올바른 Google Sheet URL을 입력해주세요."
        else:
            credentials = get_credentials()
            try:
                if action == "preview":
                    info = verify_sheet_access(credentials, src_sheet_id)
                    worksheets = info["worksheets"]
                elif action == "import":
                    src_worksheet = request.form.get("src_worksheet", "")
                    dst_sheet_id = session.get("sheet_id")
                    dst_worksheet = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)

                    # 가져오기 전 기존 제목 목록 (중복 방지용)
                    existing_map = get_items_title_map(credentials, dst_sheet_id, dst_worksheet)
                    before_count = len(existing_map)

                    count = import_from_sheet(
                        credentials, src_sheet_id, src_worksheet,
                        dst_sheet_id, dst_worksheet, existing_map
                    )

                    # 새로 추가된 항목은 목록 화면에서 청크 단위로 동기 보강한다.
                    # (백그라운드 스레드는 Cloud Run CPU 스로틀링으로 유실됨)
                    if count > 0:
                        all_items = get_all_items(credentials, dst_sheet_id, dst_worksheet)
                        new_items = all_items[before_count:]
                        new_ids = [it["id"] for it in new_items if it.get("id")]
                        if new_ids:
                            mark_pending(new_ids)
                            session["tmdb_pending_ids"] = new_ids

                    msg = f"{count}개 작품을 가져왔습니다."
                    if count > 0:
                        # 보강은 목록 화면에서 청크 단위로 진행되므로
                        # 업로드 경로와 동일하게 목록으로 이동시킨다.
                        msg += " · TMDb 검색 중..."
                        session["import_success"] = msg
                        return redirect(url_for("main.index"))
                    success = msg
            except Exception as e:
                if http_status(e) == 403:
                    logger.warning("소스 시트 접근 권한 없음 (%s)", type(e).__name__)
                    error = "소스 시트 접근 권한이 없습니다."
                else:
                    error = friendly_error(e, "가져오기에 실패했습니다",
                                           context="import_sheet", log=logger)

    return render_template(
        "import_sheet.html",
        user=session.get("user"),
        error=error,
        success=success,
        worksheets=worksheets,
        src_sheet_id=src_sheet_id,
    )


@sheet_bp.route("/upload-csv", methods=["GET", "POST"])
@login_required
def upload_csv():
    """CSV / Excel 파일을 파싱해 미리보기 후 Google Sheet에 일괄 등록."""
    from services.csv_import import parse_csv, parse_xlsx, summarize
    from services.google_sheets import append_item

    error = None
    preview = None
    summary = None

    if request.method == "POST":
        action = request.form.get("action", "preview")

        if action == "preview":
            file = request.files.get("csv_file")
            if not file or not file.filename:
                error = "파일을 선택해주세요."
            else:
                try:
                    filename = file.filename.lower()
                    content = file.read()
                    if filename.endswith((".xlsx", ".xls")):
                        items = parse_xlsx(content)
                    else:
                        items = parse_csv(content)
                    if not items:
                        error = "파일에서 유효한 데이터를 찾을 수 없습니다."
                    else:
                        summary = summarize(items)
                        preview = items
                        session["csv_import_data"] = items
                except Exception as e:
                    # 파일 파싱 오류 원문에는 경로·내부 구조가 포함될 수 있다.
                    logger.exception("CSV/Excel 파싱 실패 (%s)", type(e).__name__)
                    error = ("파일을 읽지 못했습니다. "
                             "CSV 또는 Excel(.xlsx) 형식과 열 구성을 확인해주세요.")

        elif action == "import":
            items = session.pop("csv_import_data", None)
            if not items:
                error = "가져올 데이터가 없습니다. 다시 파일을 업로드해주세요."
            elif not session.get("sheet_id"):
                return redirect(url_for("sheet.connect"))
            else:
                credentials = get_credentials()
                sheet_id = session["sheet_id"]
                worksheet_name = session.get("worksheet_name", DEFAULT_WORKSHEET_NAME)

                # ── 중복 확인: 기존 제목과 비교 ──
                existing_map = get_items_title_map(credentials, sheet_id, worksheet_name)
                new_items = []
                skipped = 0
                for item in items:
                    title_key = item.get("title", "").strip().lower()
                    if title_key and title_key in existing_map:
                        skipped += 1
                    else:
                        new_items.append(item)

                # ── 배치 저장 (한 번의 API 호출) ──
                saved_ids = append_items_batch(
                    credentials, sheet_id, new_items, worksheet_name
                )

                # item에 저장된 id 반영 (배치 함수가 id를 생성/유지)
                for item, item_id in zip(new_items, saved_ids):
                    item["id"] = item_id

                # ── TMDb 보강 예약 (목록 화면에서 청크 단위 동기 처리) ──
                if saved_ids:
                    mark_pending(saved_ids)

                msg = f"{len(new_items)}개 등록 완료"
                if skipped:
                    msg += f" ({skipped}개 중복 건너뜀)"
                if saved_ids:
                    msg += " · TMDb 검색 중..."
                session["import_success"] = msg
                session["tmdb_pending_ids"] = saved_ids
                return redirect(url_for("main.index"))

    import_success = session.pop("import_success", None)
    return render_template(
        "upload_csv.html",
        user=session.get("user"),
        error=error,
        preview=preview,
        summary=summary,
        import_success=import_success,
    )
