# 빌드 컨텍스트는 프로젝트 루트
FROM python:3.12-slim

WORKDIR /app

COPY notification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY notification-service/app ./app
COPY shared/models.py ./app/models.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
