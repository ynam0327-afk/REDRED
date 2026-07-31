from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://redis:6379/0"

    # 프론트엔드에서 브라우저로 직접 호출할 때 허용할 origin (콤마로 여러 개 구분).
    # 로컬 개발(Vite 기본 포트)은 기본값으로 이미 열어둠. ngrok으로 프론트도 띄우게 되면
    # 그 주소도 .env에 추가해야 함.
    cors_allowed_origins: str = "http://localhost:5173"

    # /events 캐싱 TTL (초). 부하테스트에서 /events가 필터 없이 호출될 때
    # occurred_at 정렬 인덱스가 없어 느렸던 게 확인되어, 인덱스 추가와 함께
    # 캐싱도 1차로 적용한다. 재난 정보라 너무 오래 캐싱하면 안 되므로 짧게 잡는다.
    events_cache_ttl_seconds: int = 10
    messages_cache_ttl_seconds: int = 10

    # 스미싱 스코어 가중합 계수 (초기값, 팀원 모델 성능 나오는 대로 재조정 예정)
    smishing_weight_url: float = 0.5
    smishing_weight_text: float = 0.5

    # 최종 스코어(0~1) 판정 임계값 (초기값)
    smishing_threshold_suspicious: float = 0.3
    smishing_threshold_danger: float = 0.6

    # FCM 실시간 푸시.
    # enable_push_scheduler는 기본 False로 둔다 - notification-service가 여러 환경(백엔드
    # 로컬 Docker, 팀원 로컬 실행 등)에서 동시에 뜰 수 있는데, 전부 켜두면 같은 이벤트에
    # 대해 중복 발송될 수 있다. 실제 발송을 담당할 인스턴스 하나에서만 .env로 켤 것.
    enable_push_scheduler: bool = False
    fcm_service_account_json_path: str = "/secrets/fcm-service-account.json"
    push_scan_interval_seconds: int = 60 # 주기 60초

    class Config:
        env_file = ".env"


settings = Settings()
