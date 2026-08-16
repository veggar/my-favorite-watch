FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# Cloud Run은 PORT 환경 변수를 자동 주입함
ENV PORT=8080

EXPOSE 8080

# gunicorn으로 실행 (Cloud Run 권장)
#
# --workers 2 유지 가능
#   TMDb 보강 진행 상태를 프로세스 메모리가 아닌 Firestore(`tmdb_jobs`)에
#   두므로, 상태 조회가 어느 워커·인스턴스로 라우팅되어도 동일한 값을 읽는다.
#   따라서 계획서 P0-3 의 단기 처방(--workers 1 / --max-instances 1 /
#   --no-cpu-throttling)은 적용하지 않는다.
#
# --timeout 120
#   보강을 백그라운드 스레드가 아니라 요청 안에서 동기 처리한다
#   (TMDB_ENRICH_CHUNK 기본 15건). 외부 API 지연을 감안해 여유를 둔다.
CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 2 --threads 8 --timeout 120 app:app
