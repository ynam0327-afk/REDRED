# 빌드 컨텍스트는 프로젝트 루트
FROM python:3.12-slim

WORKDIR /app

COPY ingest-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY ingest-worker/app ./app
COPY shared/models.py ./app/models.py

CMD ["python", "-m", "app.consumer"]
