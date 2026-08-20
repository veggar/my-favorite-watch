#!/bin/bash
# Cloud Run 배포 스크립트 - my-favorite-watch
# 사용법: bash scripts/deploy.sh
#
# 사전 준비:
#   1. gcloud auth login 완료
#   2. .env 파일에 모든 값 채워져 있는지 확인
#   3. GCP Console > API 및 서비스 > 사용자 인증 정보에서
#      REDIRECT_URI 값이 OAuth 클라이언트의 승인된 리디렉션 URI에 등록되어 있는지 확인
#      (운영: https://mfw.worldapex.studio/auth/callback)
#   4. Cloud Run 도메인 매핑(mfw.worldapex.studio)이 살아 있는지 확인
#      gcloud beta run domain-mappings list --region "$CLOUD_RUN_REGION"
#
#   5. Secret Manager 에 user-key-hmac-secret 시크릿이 있고 Cloud Run 서비스
#      계정에 secretAccessor 권한이 부여되어 있는지 확인 (SETUP.md 5.1)
#
# 배포 후 1회성 설정 (재구축·프로젝트 이전 시에도 다시 필요):
#   - Firestore tmdb_jobs / device_sessions TTL 정책, expires_at 색인 면제
#   - 절차와 명령은 SETUP.md "10. 배포 후 1회성 설정" 참조

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env 로드
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  echo "❌ .env 파일이 없습니다."
  exit 1
fi

set -o allexport
source "$PROJECT_ROOT/.env"
set +o allexport

# 필수 환경변수 확인
REQUIRED_VARS=(GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET FLASK_SECRET_KEY REDIRECT_URI)
for var in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    echo "❌ 환경변수 $var 가 설정되지 않았습니다."
    exit 1
  fi
done

PROJECT="${GOOGLE_CLOUD_PROJECT:-my-favorite-watch}"
REGION="${CLOUD_RUN_REGION:-asia-northeast3}"
SERVICE="my-favorite-watch"

# 사용자 식별 키(HMAC)는 환경 변수 값으로 배포하지 않고 Secret Manager 에서
# 주입한다. 시크릿 이름은 USER_KEY_SECRET_NAME 으로 덮어쓸 수 있다.
USER_KEY_SECRET_NAME="${USER_KEY_SECRET_NAME:-user-key-hmac-secret}"

if ! gcloud secrets describe "$USER_KEY_SECRET_NAME" --project="$PROJECT" >/dev/null 2>&1; then
  echo "❌ Secret Manager 에 '${USER_KEY_SECRET_NAME}' 시크릿이 없습니다."
  echo "   생성 절차는 SETUP.md '5.1 사용자 식별 키(HMAC)' 를 참조하세요."
  exit 1
fi

# 서비스 공개 주소.
# 커스텀 도메인(mfw.worldapex.studio)이 Cloud Run 도메인 매핑으로 연결되어 있다.
# 도메인 매핑 이전 상태로 되돌려 확인해야 하면 아래처럼 실행 시 덮어쓴다.
#   PUBLIC_BASE_URL="https://${SERVICE}-641162137323.${REGION}.run.app" bash scripts/deploy.sh
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://mfw.worldapex.studio}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL%/}"

# 배포용 REDIRECT_URI (로컬 .env의 localhost 값을 공개 주소로 대체)
DEPLOY_REDIRECT_URI="${PUBLIC_BASE_URL}/auth/callback"

# 개인정보처리방침 · 이용약관 운영 주체 정보 (P0-4)
# 미설정 상태로 배포하면 /privacy, /terms 화면에 "설정 필요" 경고가 노출되고
# Google OAuth 앱 검증(P0-2) 제출 요건도 충족하지 못한다. 배포를 막지는 않고 경고만 한다.
DEPLOY_SERVICE_URL="${SERVICE_URL:-$PUBLIC_BASE_URL}"
POLICY_VARS=(SERVICE_OPERATOR PRIVACY_CONTACT_EMAIL POLICY_EFFECTIVE_DATE)
MISSING_POLICY=()
for var in "${POLICY_VARS[@]}"; do
  if [ -z "${!var}" ]; then
    MISSING_POLICY+=("$var")
  fi
done
if [ ${#MISSING_POLICY[@]} -gt 0 ]; then
  echo "⚠️  방침·약관 운영 주체 정보 미설정: ${MISSING_POLICY[*]}"
  echo "   /privacy, /terms 화면에 '설정 필요' 경고가 표시됩니다. .env 를 확인하세요."
  echo ""
fi

echo "🚀 Cloud Run 배포 시작"
echo "   프로젝트: $PROJECT"
echo "   리전:     $REGION"
echo "   서비스:   $SERVICE"
echo "   공개 주소: $PUBLIC_BASE_URL"
echo "   REDIRECT_URI(로컬): $REDIRECT_URI"
echo "   REDIRECT_URI(배포): $DEPLOY_REDIRECT_URI"
echo "   HMAC 시크릿: ${USER_KEY_SECRET_NAME}:latest (Secret Manager)"
echo ""

cd "$PROJECT_ROOT"

# Cloud Build + Artifact Registry 권한 확인 후 배포
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET},FLASK_SECRET_KEY=${FLASK_SECRET_KEY},TMDB_API_KEY=${TMDB_API_KEY},REDIRECT_URI=${DEPLOY_REDIRECT_URI},APP_ENV=production,SERVICE_OPERATOR=${SERVICE_OPERATOR},PRIVACY_CONTACT_EMAIL=${PRIVACY_CONTACT_EMAIL},SERVICE_URL=${DEPLOY_SERVICE_URL},POLICY_EFFECTIVE_DATE=${POLICY_EFFECTIVE_DATE}" \
  --set-secrets "USER_KEY_HMAC_SECRET=${USER_KEY_SECRET_NAME}:latest"

echo ""
echo "✅ 배포 완료"
echo "   서비스 URL: ${PUBLIC_BASE_URL}"
echo "   (도메인 매핑 미적용 시: https://${SERVICE}-641162137323.${REGION}.run.app)"
