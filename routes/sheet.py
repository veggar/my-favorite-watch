import time
from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify
from routes.auth import login_required, get_credentials
from services.google_sheets import (
    extract_sheet_id,
    verify_sheet_access,
    ensure_worksheet,
    create_spreadsheet,
    import_from_sheet,
    get_all_items,
    update_item,
    DEFAULT_WORKSHEET_NAME,
    HEADERS,
    DELETED_HEADERS,
    DELETED_WORKSHEET_NAME,
)
from services.tmdb import enrich_item, enrich_items_batch

sheet_bp = Blueprint("sheet", __name__)


def _save_sheet_session(sheet_id: str, sheet_title: str, worksheet_name: str):
    session["sheet_id"] = sheet_id
    session["sheet_title"] = sheet_title
    session["worksheet_name"] = worksheet_name


@sheet_bp.route("/connect", methods=["GET", "POST"])
@login_required
def connect():
    error = None
    if request.method == "POST":
        action = request.form.get("action", "connect")

        # ── 새 시트 문서 생성 ──
        if action == "create":
            doc_title = request.form.get("doc_title", "My Favorite Watch").strip() or "My Favorite Watch"
            worksheet_name = request.form.get("worksheet_name", DEFAULT_WORKSHEET_NAME).strip() or DEFAULT_WORKSHEET_NAME
            credentials = get_credentials()
            try:
                result = create_spreadsheet(credentials, doc_title, worksheet_name)
                _save_sheet_session(result["sheet_id"], doc_title, worksheet_name)
                return redirect(url_for("main.index"))
            except Exception as e:
                error = f"시트 생성에 실패했습니다: {e}"

        # ── 기존 시트 연결 ──
        elif action == "connect":
            sheet_url = request.form.get("sheet_url", "").strip()
            worksheet_name = request.form.get("worksheet_name", DEFAULT_WORKSHEET_NAME).strip() or DEFAULT_WORKSHEET_NAME
            sheet_id = extract_sheet_id(sheet_url)

            if not sheet_id:
                error = "올바른 Google Sheet URL을 입력해주세요."
            else:
                credentials = get_credentials()
                try:
                    info = verify_sheet_access(credentials, sheet_id)
                    ensure_worksheet(credentials, sheet_id, worksheet_name, HEADERS)
                    ensure_worksheet(credentials, sheet_id, DELETED_WORKSHEET_NAME, DELETED_HEADERS)
                    _save_sheet_session(sheet_id, info["title"], worksheet_name)
                    return redirect(url_for("main.index"))
                except Exception as e:
                    err_str = str(e)
                    if "403" in err_str:
                        error = "시트 접근 권한이 없습니다."
                    elif "404" in err_str:
                        error = "시트를 찾을 수 없습니다."
                    else:
                        error = f"연결에 실패했습니다: {err_str}"

    return render_template("connect.html", user=session.get("user"), error=error,
                           default_worksheet=DEFAULT_WORKSHEET_NAME)


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

                    # 가져오기 전 기존 항목 수 기록
                    before = get_all_items(credentials, dst_sheet_id, dst_worksheet)
                    before_count = len(before)

                    count = import_from_sheet(
                        credentials, src_sheet_id, src_worksheet,
                        dst_sheet_id, dst_worksheet
                    )

                    # 새로 추가된 항목만 TMDb 보강 후 시트에 업데이트
                    enriched = 0
                    if count > 0:
                        all_items = get_all_items(credentials, dst_sheet_id, dst_worksheet)
                        new_items = all_items[before_count:]
                        for i, item in enumerate(new_items):
                            if i > 0:
                                time.sleep(0.1)
                            if enrich_item(item):
                                data = dict(item)
                                data["watched"] = item.get("watched", "").lower() == "true"
                                update_item(credentials, dst_sheet_id, item["id"], data, dst_worksheet)
                                enriched += 1

                    success = f"{count}개 작품을 가져왔습니다."
                    if enriched:
                        success += f" (TMDb 링크 {enriched}개 자동 연결)"
            except Exception as e:
                err_str = str(e)
                if "403" in err_str:
                    error = "소스 시트 접근 권한이 없습니다."
                else:
                    error = f"가져오기에 실패했습니다: {err_str}"

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
    """CSV 파일을 파싱해 미리보기 후 Google Sheet에 일괄 등록."""
    from services.csv_import import parse_csv, summarize
    from services.google_sheets import append_item

    error = None
    preview = None
    summary = None

    if request.method == "POST":
        action = request.form.get("action", "preview")

        if action == "preview":
            file = request.files.get("csv_file")
            if not file or not file.filename:
                error = "CSV 파일을 선택해주세요."
            else:
                try:
                    content = file.read()
                    items = parse_csv(content)
                    if not items:
                        error = "파일에서 유효한 데이터를 찾을 수 없습니다."
                    else:
                        summary = summarize(items)
                        preview = items[:20]  # 최대 20건 미리보기
                        session["csv_import_data"] = items  # 임시 저장
                except Exception as e:
                    error = f"파싱 실패: {e}"

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

                # TMDb로 titleLink / officialRating 보강 (삽입 전)
                enriched = enrich_items_batch(items)

                success_count = 0
                fail_count = 0
                for item in items:
                    try:
                        append_item(credentials, sheet_id, item, worksheet_name)
                        success_count += 1
                    except Exception:
                        fail_count += 1

                msg = f"{success_count}개 등록 완료"
                if enriched:
                    msg += f" (TMDb 링크 {enriched}개 자동 연결)"
                if fail_count:
                    msg += f" ({fail_count}개 실패)"
                session["import_success"] = msg
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
