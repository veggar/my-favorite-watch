#!/bin/bash
# Cloud Run 배포 스크립트 - my-favorite-watch
# 사용법: bash scripts/deploy.sh
#
# 사전 준비:
#   1. gcloud auth login 완료
#   2. .env 파일에 모든 값 채워져 있는지 확인
#   3. GCP Console > API 및 서비스 > 사용자 인증 정보에서
#      REDIRECT_URI 값이 OAuth 클라이언트의 승인된 리디렉션 URI에 등록되어 있는지 확인

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

echo "🚀 Cloud Run 배포 시작"
echo "   프로젝트: $PROJECT"
echo "   리전:     $REGION"
echo "   서비스:   $SERVICE"
echo "   REDIRECT_URI: $REDIRECT_URI"
echo ""

cd "$PROJECT_ROOT"

# Cloud Run용 REDIRECT_URI (로컬 .env의 localhost 값을 Cloud Run URL로 대체)
CLOUDRUN_REDIRECT_URI="https://${SERVICE}-641162137323.${REGION}.run.app/auth/callback"

# Cloud Build + Artifact Registry 권한 확인 후 배포
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET},FLASK_SECRET_KEY=${FLASK_SECRET_KEY},TMDB_API_KEY=${TMDB_API_KEY},REDIRECT_URI=${CLOUDRUN_REDIRECT_URI},APP_ENV=production"

echo ""
echo "✅ 배포 완료"
echo "   서비스 URL: https://${SERVICE}-641162137323.${REGION}.run.app"
