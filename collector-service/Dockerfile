# 빌드 컨텍스트는 프로젝트 루트 (docker-compose.yml의 context: . 참고)
FROM python:3.12-slim

WORKDIR /app

COPY collector-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY collector-service/app ./app

CMD ["python", "-m", "app.main"]
