from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from routes.auth import login_required, get_credentials
from services.google_sheets import (
    extract_sheet_id,
    verify_sheet_access,
    ensure_worksheet,
    WORKSHEET_NAME,
    HEADERS,
)

sheet_bp = Blueprint("sheet", __name__)


@sheet_bp.route("/connect", methods=["GET", "POST"])
@login_required
def connect():
    error = None
    if request.method == "POST":
        sheet_url = request.form.get("sheet_url", "").strip()
        sheet_id = extract_sheet_id(sheet_url)

        if not sheet_id:
            error = "올바른 Google Sheet URL을 입력해주세요."
        else:
            credentials = get_credentials()
            try:
                info = verify_sheet_access(credentials, sheet_id)
                ensure_worksheet(credentials, sheet_id, WORKSHEET_NAME, HEADERS)
                session["sheet_id"] = sheet_id
                session["sheet_title"] = info["title"]
                return redirect(url_for("main.index"))
            except Exception as e:
                err_str = str(e)
                if "403" in err_str:
                    error = "시트 접근 권한이 없습니다. 해당 시트에 대한 편집 권한을 확인해주세요."
                elif "404" in err_str:
                    error = "시트를 찾을 수 없습니다. URL을 다시 확인해주세요."
                else:
                    error = f"연결에 실패했습니다: {err_str}"

    return render_template("connect.html", user=session.get("user"), error=error)
