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
CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 2 --threads 8 --timeout 60 app:app
