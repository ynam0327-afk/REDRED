# RedRed - 소방안전 재난 알림 MSA 스캐폴드

## 구조
```
redred-scaffold/
├── docker-compose.yml       # DB + Redis + 3개 서비스 한 번에 기동
├── .env.example              # 이걸 복사해서 .env로 만들고 실제 키 채우기
├── shared/
│   ├── schema.sql             # DB 스키마 (postgres 최초 기동 시 자동 실행)
│   └── models.py               # Pydantic 모델 (ingest-worker, notification-service가 복사해서 사용)
├── collector-service/         # 3개 소방청 API를 주기적으로 호출 -> Redis Stream에 push
├── ingest-worker/              # Redis Stream 소비 -> normalized_events 테이블에 적재
└── notification-service/       # FastAPI, /events로 저장된 이벤트 조회 (다음 단계: 실제 푸시 발송 추가)
```

## 실행 방법

1. 환경변수 설정
   ```bash
   cp .env.example .env
   # .env 파일 열어서 BIGDATA119_API_KEY 실제 값으로 교체
   ```

2. 전체 기동
   ```bash
   docker compose up --build
   ```

3. 확인
   - `docker compose logs -f collector-service` : API 호출 및 Redis Stream 적재 로그
   - `docker compose logs -f ingest-worker` : DB 적재 로그
   - http://localhost:8000/health : notification-service 헬스체크
   - http://localhost:8000/events?sido=서울특별시 : 서울 지역 최신 이벤트 조회
   - http://localhost:8000/docs : FastAPI 자동 생성 API 문서 (Swagger)

## 지금 단계에서 아직 구현되지 않은 것 (다음 단계 후보)

- `notification-service`의 실제 FCM 푸시 발송 로직 (지금은 조회 API만 있음)
- `raw_call_receipts` / `raw_fire_incidents` / `raw_rescue_incidents` 원본 테이블 upsert
  (`ingest-worker/app/consumer.py`는 현재 `normalized_events`에만 적재하도록 단순화되어 있음)
- 스미싱 차단(URL 탐지) 서비스 - 아직 이 스캐폴드에 포함 안 됨
- 재시도/Dead Letter Queue 처리 (지금은 메시지 처리 실패 시 ACK을 안 보내고 넘어가는 최소 구현)
- 테스트 코드

## 폴링 주기 조정

`.env`의 `POLL_INTERVAL_SECONDS`를 조정하세요. 실제 소방청 데이터 배치 갱신 주기를
경험적으로 확인한 뒤(며칠간 gtrRegDt 값 변화 관찰) 이 값을 현실에 맞게 다시 설정하는 걸 권장합니다.
