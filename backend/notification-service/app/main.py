"""
notification-service

지금 단계 범위: normalized_events를 조회하는 API + 스미싱 판별 결과(incoming_messages)를
받아 저장/조회하는 최소 API를 제공한다.
FCM 발송 로직(사용자 위치 매칭, 큐 소비, 실제 push)은 다음 단계에서 추가한다.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import asyncpg
import json
import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import push
from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        dsn=settings.database_url.replace("postgresql+asyncpg://", "postgresql://"),
        min_size=5,
        max_size=15,  # 30까지 늘렸다가 CPU 경쟁으로 /health까지 느려지는 역효과 확인 -> 절충값으로 하향
    )
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.cache_locks: dict[str, asyncio.Lock] = {}  # 캐시 스탬피드 방지용 (아래 get_or_compute_cached 참고)

    scheduler = None
    if settings.enable_push_scheduler: # 켜져있을때만
            push.init_firebase()
            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                push.send_pending_notifications,
                "interval",
                seconds=settings.push_scan_interval_seconds,
                args=[app.state.pool],
            )
            scheduler.start()
            logger.info("FCM 발송 스케줄러 시작 (주기=%d초)", settings.push_scan_interval_seconds) # 보통 60초
    else:
            logger.info("FCM 발송 스케줄러 비활성화 상태 (이 인스턴스는 발송 안 함)")
    
    yield
    
    if scheduler is not None:
            scheduler.shutdown()
    await app.state.redis.aclose()
    await app.state.pool.close()

app = FastAPI(title="RedRed Notification Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EventOut(BaseModel):
    event_id: str
    incident_type: str
    occurred_at: datetime
    sido_nm: Optional[str]
    sigungu_nm: Optional[str]
    eupmyeondong_nm: Optional[str]
    lon: Optional[float]
    lat: Optional[float]
    location_precision: str
    summary_title: Optional[str]
    severity_hint: Optional[str]
    is_notified: bool


@app.get("/health")
async def health():
    return {"status": "ok"}


async def get_or_compute_cached(cache_key: str, ttl: int, compute_fn) -> str:
    """
    cache-aside + 스탬피드 방지.

    부하테스트 확인 완료 사항::
    캐시 TTL이 만료되는 순간 동시 요청이 몰리면, 캐시가 비어있으니 전부 DB로 몰려가서 
    그 순간만 지연시간이 튄다(p50은 좋아져도 max가 오히려 나빠지는 이유).
    이 함수는 그 순간에도 실제 DB 조회는 딱 1번만 일어나게 하고, 나머지
    요청은 그 결과가 캐시에 채워질 때까지 기다렸다가 재사용하게 한다.

    주의: 락을 프로세스 메모리(dict)에 두고 있어서, notification-service를 여러 인스턴스로
    수평 확장하면 인스턴스별로만 스탬피드가 방지된다 (완전한 분산 락은 아님). 
    나중에 여러 인스턴스로 나눠 띄우게 되면 Redis 기반 분산 락으로 바꿔야 한다.
    """
    cached = await app.state.redis.get(cache_key)
    if cached is not None:
        return cached

    lock = app.state.cache_locks.setdefault(cache_key, asyncio.Lock())
    async with lock:
        # 락을 기다리는 동안 다른 요청이 이미 채워놨을 수 있으니 다시 확인 (double-checked locking)
        cached = await app.state.redis.get(cache_key)
        if cached is not None:
            return cached

        payload = await compute_fn()
        await app.state.redis.set(cache_key, payload, ex=ttl)
        return payload


@app.get("/events", response_model=list[EventOut])
async def list_events(
    sido: Optional[str] = Query(None, description="시도명으로 필터 (예: 서울특별시)"),
    sigungu: Optional[str] = Query(None, description="시군구명으로 필터 (예: 강남구)"),
    incident_type: Optional[str] = Query(None, description="FIRE / RESCUE / CALL_RECEIPT"),
    only_unnotified: bool = Query(False, description="아직 알림 발송 안 된 건만 조회"),
    limit: int = Query(50, le=200),
):
    """지역/유형별로 최신 이벤트를 조회한다. (알림 발송 서비스 다음 단계에서 이 쿼리를 재사용)"""
    cache_key = f"cache:events:{sido}:{sigungu}:{incident_type}:{only_unnotified}:{limit}"

    async def _compute() -> str:
        conditions = []
        params: list = []

        def add_condition(sql: str, value):
            params.append(value)
            conditions.append(sql.format(idx=len(params)))

        if sido:
            add_condition("sido_nm = ${idx}", sido)
        if sigungu:
            add_condition("sigungu_nm = ${idx}", sigungu)
        if incident_type:
            add_condition("incident_type = ${idx}", incident_type)
        if only_unnotified:
            conditions.append("is_notified = FALSE")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        query = f"""
            SELECT event_id, incident_type, occurred_at, sido_nm, sigungu_nm, eupmyeondong_nm,
                   lon, lat, location_precision, summary_title, severity_hint, is_notified
            FROM normalized_events
            {where_clause}
            ORDER BY occurred_at DESC
            LIMIT ${len(params)}
        """

        async with app.state.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        events = [EventOut(**dict(row)) for row in rows]
        return json.dumps([e.model_dump(mode="json") for e in events], ensure_ascii=False)

    payload = await get_or_compute_cached(cache_key, settings.events_cache_ttl_seconds, _compute)
    return Response(content=payload, media_type="application/json")


# =====================================================================
# 스미싱 판별 (incoming_messages)
#
# 이 서비스는 URL/텍스트 모델을 직접 돌리지 않는다. 팀원 모델이 이미 계산한
# url_risk_score / text_authenticity_score를 입력으로 받아, 규칙 기반
# 가중합으로 최종 smishing_score와 verdict만 계산해서 저장·조회한다.
# 가중치·임계값은 config.py의 초기값이며 팀원 모델 성능이 나오는 대로 조정 예정.
# =====================================================================

class MessageScoreIn(BaseModel):
    received_at: datetime
    raw_text: str = Field(..., max_length=4000)
    detected_urls: Optional[list[str]] = None
    url_risk_score: float = Field(..., ge=0, le=1, description="팀원 악성 URL 모델 출력 (0~1, 높을수록 위험)")
    text_authenticity_score: float = Field(..., ge=0, le=1, description="팀원 재난문자 분류 모델 출력 (0~1, 높을수록 공식 문자에 가까움)")
    matched_sido_nm: Optional[str] = None
    matched_sigungu_nm: Optional[str] = None
    matched_event_id: Optional[str] = Field(None, description="공식 DB(normalized_events)에서 매칭된 event_id, 없으면 생략")
    device_id: Optional[str] = None


class MessageOut(BaseModel):
    message_id: int
    received_at: datetime
    raw_text: str
    detected_urls: Optional[list[str]]
    url_risk_score: Optional[float]
    text_authenticity_score: Optional[float]
    matched_sido_nm: Optional[str]
    matched_sigungu_nm: Optional[str]
    matched_event_id: Optional[str]
    smishing_score: float
    verdict: str
    device_id: Optional[str]
    created_at: datetime


class EventBrief(BaseModel):
    event_id: str
    summary_title: Optional[str]
    occurred_at: datetime
    sido_nm: Optional[str]
    sigungu_nm: Optional[str]


class MessageDetailOut(MessageOut):
    matched_event: Optional[EventBrief] = None


def compute_smishing_score(url_risk_score: float, text_authenticity_score: float) -> tuple[float, str]:
    """
    규칙 기반 가중합. text_authenticity_score는 "공식 문자와 얼마나 비슷한가"이므로
    위험도 방향으로 뒤집어서((1 - text_authenticity_score)) url_risk_score와 합산한다.
    """
    score = (
        settings.smishing_weight_url * url_risk_score
        + settings.smishing_weight_text * (1 - text_authenticity_score)
    )
    score = max(0.0, min(1.0, score))

    if score >= settings.smishing_threshold_danger:
        verdict = "SMISHING"
    elif score >= settings.smishing_threshold_suspicious:
        verdict = "SUSPICIOUS"
    else:
        verdict = "AUTHENTIC"

    return round(score, 3), verdict


@app.post("/messages", response_model=MessageOut)
async def create_message(body: MessageScoreIn):
    """수신 문자 1건 + 컴포넌트 스코어를 받아 최종 smishing_score/verdict를 계산해 저장한다."""
    smishing_score, verdict = compute_smishing_score(body.url_risk_score, body.text_authenticity_score)

    # DB의 received_at은 TIMESTAMP(시간대 정보 없음)라서, 클라이언트가 'Z'(UTC) 등
    # 시간대 정보를 붙여 보내면 asyncpg가 바로 에러를 낸다. 시간대 정보는 버리고
    # 값 그대로(naive)를 저장한다 (이 프로젝트는 KST 단일 시간대 가정).
    received_at = body.received_at.replace(tzinfo=None) if body.received_at.tzinfo else body.received_at

    query = """
        INSERT INTO incoming_messages (
            received_at, raw_text, detected_urls, url_risk_score, text_authenticity_score,
            matched_sido_nm, matched_sigungu_nm, matched_event_id,
            smishing_score, verdict, device_id
        ) VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING message_id, received_at, raw_text, detected_urls, url_risk_score, text_authenticity_score,
                  matched_sido_nm, matched_sigungu_nm, matched_event_id, smishing_score, verdict,
                  device_id, created_at
    """
    try:
        async with app.state.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                received_at, body.raw_text,
                json.dumps(body.detected_urls) if body.detected_urls is not None else None,
                body.url_risk_score, body.text_authenticity_score,
                body.matched_sido_nm, body.matched_sigungu_nm, body.matched_event_id,
                smishing_score, verdict, body.device_id,
            )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(status_code=400, detail=f"matched_event_id={body.matched_event_id!r}가 normalized_events에 없습니다.")

    result = dict(row)
    result["detected_urls"] = json.loads(result["detected_urls"]) if result["detected_urls"] else None
    return MessageOut(**result)


@app.get("/messages", response_model=list[MessageOut])
async def list_messages(
    device_id: Optional[str] = Query(None, description="단말 ID로 필터"),
    verdict: Optional[str] = Query(None, description="AUTHENTIC / SUSPICIOUS / SMISHING"),
    limit: int = Query(50, le=200),
):
    """탐지 이력 대시보드용 목록 조회."""
    cache_key = f"cache:messages:{device_id}:{verdict}:{limit}"

    async def _compute() -> str:
        conditions = []
        params: list = []

        def add_condition(sql: str, value):
            params.append(value)
            conditions.append(sql.format(idx=len(params)))

        if device_id:
            add_condition("device_id = ${idx}", device_id)
        if verdict:
            add_condition("verdict = ${idx}", verdict)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        query = f"""
            SELECT message_id, received_at, raw_text, detected_urls, url_risk_score, text_authenticity_score,
                   matched_sido_nm, matched_sigungu_nm, matched_event_id, smishing_score, verdict,
                   device_id, created_at
            FROM incoming_messages
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params)}
        """

        async with app.state.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            d = dict(row)
            d["detected_urls"] = json.loads(d["detected_urls"]) if d["detected_urls"] else None
            results.append(MessageOut(**d))
        return json.dumps([m.model_dump(mode="json") for m in results], ensure_ascii=False)

    payload = await get_or_compute_cached(cache_key, settings.messages_cache_ttl_seconds, _compute)
    return Response(content=payload, media_type="application/json")


@app.get("/messages/{message_id}", response_model=MessageDetailOut)
async def get_message(message_id: int):
    """상세: 수신 문자 vs 공식 재난문자 DB 비교 판별 화면용. matched_event_id가 있으면 공식 사건 정보를 같이 반환한다."""
    query = """
        SELECT
            m.message_id, m.received_at, m.raw_text, m.detected_urls, m.url_risk_score,
            m.text_authenticity_score, m.matched_sido_nm, m.matched_sigungu_nm, m.matched_event_id,
            m.smishing_score, m.verdict, m.device_id, m.created_at,
            e.event_id AS ev_event_id, e.summary_title AS ev_summary_title,
            e.occurred_at AS ev_occurred_at, e.sido_nm AS ev_sido_nm, e.sigungu_nm AS ev_sigungu_nm
        FROM incoming_messages m
        LEFT JOIN normalized_events e ON e.event_id = m.matched_event_id
        WHERE m.message_id = $1
    """
    async with app.state.pool.acquire() as conn:
        row = await conn.fetchrow(query, message_id)

    if row is None:
        raise HTTPException(status_code=404, detail="해당 message_id를 찾을 수 없습니다.")

    d = dict(row)
    d["detected_urls"] = json.loads(d["detected_urls"]) if d["detected_urls"] else None

    matched_event = None
    if d["matched_event_id"]:
        matched_event = EventBrief(
            event_id=d["ev_event_id"],
            summary_title=d["ev_summary_title"],
            occurred_at=d["ev_occurred_at"],
            sido_nm=d["ev_sido_nm"],
            sigungu_nm=d["ev_sigungu_nm"],
        )

    return MessageDetailOut(matched_event=matched_event, **{k: v for k, v in d.items() if not k.startswith("ev_")})

# =====================================================================
# FCM 단말 토큰 등록
# =====================================================================

class DeviceTokenIn(BaseModel):
    token: str = Field(..., description="FCM이 앱 설치 단위로 발급하는 토큰")
    device_id: Optional[str] = Field(None, description="incoming_messages.device_id와 동일 개념 (선택)")
    platform: Optional[str] = Field(None, description="android / ios / web 등 (선택)")


@app.post("/device-tokens")
async def register_device_token(body: DeviceTokenIn):
    """앱 실행 시 FCM 토큰을 등록/갱신한다. 같은 토큰이 다시 오면 last_seen_at만 갱신한다."""
    async with app.state.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO device_tokens (token, device_id, platform, last_seen_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
            ON CONFLICT (token) DO UPDATE SET
                device_id = EXCLUDED.device_id,
                platform = EXCLUDED.platform,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            body.token, body.device_id, body.platform,
        )
    return {"status": "ok"}
