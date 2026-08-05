"""사용자용 오류 메시지와 서버 로그를 분리하는 유틸.

Google API 오류 본문에는 내부 식별자 · 요청 정보 · 계정 정보가 포함될 수
있으므로 예외 문자열을 화면에 그대로 렌더링하지 않는다.
(`.claude/rules/security.md` "Sanitization")

원칙
- 화면에는 원인별로 미리 정의된 안내 문구만 노출한다.
- 예외 원문과 스택은 `logger.exception` 으로 서버 로그에만 남긴다.
"""
import logging
import re

logger = logging.getLogger(__name__)

GENERIC_MESSAGE = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

# HTTP 상태 코드 → 사용자 안내 문구
_STATUS_MESSAGES = {
    400: "요청 형식이 올바르지 않습니다.",
    401: "인증이 만료되었습니다. 다시 로그인해주세요.",
    403: "접근 권한이 없습니다.",
    404: "대상을 찾을 수 없습니다.",
    409: "다른 곳에서 먼저 변경되었습니다. 새로고침 후 다시 시도해주세요.",
    429: "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
    500: "서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.",
    502: "서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.",
    503: "서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.",
    504: "서비스 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.",
}


def http_status(exc: Exception) -> int | None:
    """예외에서 HTTP 상태 코드를 최대한 안전하게 추출한다."""
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value

    resp = getattr(exc, "resp", None)  # googleapiclient.errors.HttpError
    status = getattr(resp, "status", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            pass

    # 위 경로가 모두 실패하면 메시지에서 상태 코드 패턴을 찾는다.
    match = re.search(r"\b(4\d{2}|5\d{2})\b", str(exc))
    if match:
        return int(match.group(1))
    return None


def friendly_error(exc: Exception, prefix: str = "", *,
                   context: str = "", log: logging.Logger | None = None) -> str:
    """사용자에게 보여줄 안전한 메시지를 반환하고 원문은 로그로만 남긴다.

    Args:
        exc: 발생한 예외
        prefix: "시트 생성에 실패했습니다" 처럼 상황을 알려주는 접두 문구
        context: 로그 식별용 문자열 (사용자에게 노출되지 않음)
        log: 사용할 로거 (기본값: 이 모듈의 로거)

    Returns:
        예외 원문이 포함되지 않은 사용자용 메시지
    """
    (log or logger).exception("%s 실패 (%s)", context or prefix or "작업", type(exc).__name__)

    detail = _STATUS_MESSAGES.get(http_status(exc) or 0, GENERIC_MESSAGE)
    if not prefix:
        return detail
    if detail is GENERIC_MESSAGE:
        return f"{prefix}. 잠시 후 다시 시도해주세요."
    return f"{prefix}. {detail}"
