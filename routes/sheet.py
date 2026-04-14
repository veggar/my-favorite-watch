from flask import Blueprint, render_template, request, session, redirect, url_for
from routes.auth import login_required, get_credentials
from services.google_sheets import (
    extract_sheet_id,
    verify_sheet_access,
    ensure_worksheet,
    create_spreadsheet,
    import_from_sheet,
    DEFAULT_WORKSHEET_NAME,
    HEADERS,
    DELETED_HEADERS,
    DELETED_WORKSHEET_NAME,
)

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
                    count = import_from_sheet(
                        credentials, src_sheet_id, src_worksheet,
                        dst_sheet_id, dst_worksheet
                    )
                    success = f"{count}개 작품을 가져왔습니다."
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
