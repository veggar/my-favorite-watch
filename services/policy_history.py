"""개인정보처리방침·이용약관의 이전 버전 보관 (PRD §5.1).

"개인정보처리방침 변경 시 시행일과 이전 버전을 함께 제공한다"는 요구사항을
만족하기 위해, 콘텐츠를 바꾸기 **직전**에 현재 라이브 화면을 그대로 얼려
`docs/legal/history/{privacy,terms}/{effective_date}.html`로 저장한다.
`/privacy`, `/terms`는 저장된 스냅샷이 있으면 하단에 "이전 버전" 링크를
보여준다.

스냅샷은 `scripts/archive_policy_snapshot.py`로 만든다(운영자가 콘텐츠를
바꾸기 전에 수동 실행). 이 모듈은 저장·조회만 담당하며, 렌더링은
`routes/site.py`가 한다.

경로 안전
    `doc_type`은 "privacy"/"terms" 둘 중 하나만 허용한다. `effective_date`는
    URL 경로 파라미터로 들어오므로 영문·숫자·`-`·`_`·`.`만 허용해
    디렉터리 탈출을 막는다.
"""
from __future__ import annotations

import re
from pathlib import Path

HISTORY_ROOT = Path(__file__).resolve().parent.parent / "docs" / "legal" / "history"
DOC_TYPES = ("privacy", "terms")

# 파일명(=시행일) 허용 문자. 예: 2026-08-20, 2026-08-20_v2
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9_.-]+$")


def _dir_for(doc_type: str) -> Path | None:
    if doc_type not in DOC_TYPES:
        return None
    return HISTORY_ROOT / doc_type


def is_safe_slug(slug: str) -> bool:
    return bool(slug) and bool(_SAFE_SLUG.match(slug)) and ".." not in slug


def list_versions(doc_type: str) -> list[str]:
    """저장된 스냅샷의 시행일(파일명) 목록을 최신순으로 돌려준다."""
    directory = _dir_for(doc_type)
    if directory is None or not directory.is_dir():
        return []
    slugs = [p.stem for p in directory.glob("*.html") if is_safe_slug(p.stem)]
    return sorted(slugs, reverse=True)


def read_version(doc_type: str, slug: str) -> str | None:
    """스냅샷 HTML 원문을 읽는다. 없거나 경로가 안전하지 않으면 None."""
    directory = _dir_for(doc_type)
    if directory is None or not is_safe_slug(slug):
        return None
    path = directory / f"{slug}.html"
    try:
        # HISTORY_ROOT 밖으로 나가지 못하도록 최종 경로도 다시 확인한다.
        path = path.resolve()
        if directory.resolve() not in path.parents:
            return None
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def write_version(doc_type: str, slug: str, html: str) -> Path:
    """현재 화면 HTML을 스냅샷으로 저장한다. 이미 있으면 덮어쓰지 않는다."""
    directory = _dir_for(doc_type)
    if directory is None:
        raise ValueError(f"알 수 없는 문서 종류: {doc_type}")
    if not is_safe_slug(slug):
        raise ValueError(f"시행일 형식이 올바르지 않습니다: {slug}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.html"
    if path.exists():
        raise FileExistsError(f"이미 저장된 스냅샷입니다: {path}")
    path.write_text(html, encoding="utf-8")
    return path
