"""
notification-service

지금 단계 범위: normalized_events를 조회하는 API + 스미싱 판별 결과(incoming_messages)를
받아 저장/조회하는 최소 API를 제공한다.
FCM 발송 로직(사용자 위치 매칭, 큐 소비, 실제 push)은 다음 단계에서 추가한다.
"""
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml"))
from smishing_pipeline import process_message

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
        max_size=15,
    )
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)

    # cache_key가 필터 조합마다 다 달라서 계속 늘어나기만 하면 안 되니,
    # 고정된 개수(64개)의 버킷에 해시로 분산해 재사용한다 (무한정 커지는 딕셔너리 방지).
    app.state.cache_locks: list[asyncio.Lock] = [asyncio.Lock() for _ in range(64)]

    scheduler = None
    if settings.enable_push_scheduler:
        push.init_firebase()
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            push.send_pending_notifications,
            "interval",
            seconds=settings.push_scan_interval_seconds,
            args=[app.state.pool],
        )
        scheduler.start()
        logger.info("FCM 발송 스케줄러 시작 (주기=%d초)", settings.push_scan_interval_seconds)
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


class EventDetailOut(EventOut):
    full_text: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok"}


async def get_or_compute_cached(cache_key: str, ttl: int, compute_fn) -> str:
    cached = await app.state.redis.get(cache_key)
    if cached is not None:
        return cached

    lock = app.state.cache_locks[hash(cache_key) % len(app.state.cache_locks)]
    async with lock:
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


@app.get("/events/{event_id}", response_model=EventDetailOut)
async def get_event_detail(event_id: str):
    async with app.state.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT event_id, incident_type, occurred_at, sido_nm, sigungu_nm, eupmyeondong_nm,
                   lon, lat, location_precision, summary_title, severity_hint, is_notified, source_pk
            FROM normalized_events WHERE event_id = $1
            """,
            event_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="해당 event_id를 찾을 수 없습니다.")

        d = dict(row)
        full_text = None
        if d["incident_type"] == "OFFICIAL_ALERT":
            alert_row = await conn.fetchrow(
                "SELECT msg_cn FROM raw_official_alerts WHERE sn = $1",
                int(d["source_pk"]),
            )
            if alert_row:
                full_text = alert_row["msg_cn"]

    return EventDetailOut(full_text=full_text, **{k: v for k, v in d.items() if k != "source_pk"})


# =====================================================================
# 스미싱 판별 (incoming_messages)
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
    is_disaster_message: Optional[bool] = Field(
        None, description="재난문자 형식/어휘 자체가 있는지 여부. None이면 기존처럼 판단(True 취급)"
    )


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


def contains_ip_url(urls: list[str] | None) -> bool:
    """detected_urls 중 IP 주소 형태(도메인 없이 숫자.숫자.숫자.숫자)가 하나라도 있는지."""
    if not urls:
        return False

    ip_pattern = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
    return any(ip_pattern.search(url) for url in urls)


def compute_smishing_score(
    url_risk_score: float,
    text_authenticity_score: float,
    detected_urls: list[str] | None = None,
    is_disaster_message: Optional[bool] = True,
) -> tuple[float, str]:
    """
    Rule 1: detected_urls에 IP 주소 URL이 있으면 즉시 SMISHING (도메인 없이 IP로 직접
            접속을 유도하는 링크는 정상적인 공식 문자에선 나올 이유가 없음)
    Rule 2: url_risk_score가 0.8 이상이면 즉시 SMISHING
    Rule 3: 그 외엔 가중합 (URL 비중 0.7 / 텍스트 비중 0.3)

    is_disaster_message=False (재난문자 형식/어휘 자체가 전혀 없는 일반 문자)인 경우엔
    text_authenticity_score가 의미 없는 값이므로 가중합에 반영하지 않는다. 대신 URL 관련
    규칙(IP URL, 고위험 URL)은 재난 여부와 무관하게 그대로 적용해서 위험한 링크는 놓치지 않되,
    위험하지 않으면 SMISHING/SUSPICIOUS/AUTHENTIC이 아니라 별도의 NOT_DISASTER로 분리한다.
    """
    if contains_ip_url(detected_urls):
        return 1.0, "SMISHING"

    if url_risk_score >= 0.8:
        return 1.0, "SMISHING"

    if is_disaster_message is False:
        score = max(0.0, min(1.0, url_risk_score))
        return round(score, 3), "NOT_DISASTER"

    score = (
        0.7 * url_risk_score
        + 0.3 * (1 - text_authenticity_score)
    )
    score = max(0.0, min(1.0, score))

    if score >= 0.7:
        verdict = "SMISHING"
    elif score >= 0.3:
        verdict = "SUSPICIOUS"
    else:
        verdict = "AUTHENTIC"

    return round(score, 3), verdict


class AnalyzeRequest(BaseModel):
    raw_text: str = Field(..., max_length=4000)
    device_id: Optional[str] = None


@app.post("/analyze", response_model=MessageOut)
async def analyze_message(req: AnalyzeRequest):
    """
    사용자가 문자를 붙여넣었을 때 호출되는 엔드포인트.
    raw_text 하나로 url_risk_score/text_authenticity_score까지 계산한 뒤,
    기존 create_message() 로직(compute_smishing_score + DB 저장)을 그대로 재사용한다.

    process_message()는 pandas 필터링/RF 모델 추론뿐 아니라 공식 API 호출(최대 3회 재시도,
    합쳐서 수십 초까지 걸릴 수 있음)까지 포함한 무거운 동기(blocking) 작업이라,
    asyncio.to_thread로 별도 스레드에서 돌려야 한다. 여기서 await 없이 직접 호출하면
    그 시간 동안 이 프로세스(uvicorn 워커 1개)의 이벤트루프 전체가 멈춰서,
    다른 사용자의 모든 요청(/messages, /events, /health 포함)이 같이 막힌다.
    """
    scores = await asyncio.to_thread(
        process_message,
        raw_text=req.raw_text,
        sms_date=datetime.now().date().isoformat(),
        official_service_key=os.environ.get("SAFETYDATA_SERVICE_KEY"),
    )

    body = MessageScoreIn(
        received_at=datetime.now(),
        raw_text=req.raw_text,
        detected_urls=[scores["detail"]["url_used"]] if scores["detail"]["url_used"] else None,
        url_risk_score=scores["url_risk_score"],
        text_authenticity_score=scores["text_authenticity_score"],
        device_id=req.device_id,
        is_disaster_message=scores.get("is_disaster_message", True),
    )

    return await create_message(body)


@app.post("/messages", response_model=MessageOut)
async def create_message(body: MessageScoreIn):
    """수신 문자 1건 + 컴포넌트 스코어를 받아 최종 smishing_score/verdict를 계산해 저장한다."""
    smishing_score, verdict = compute_smishing_score(
        body.url_risk_score,
        body.text_authenticity_score,
        body.detected_urls,
        body.is_disaster_message,
    )

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
    verdict: Optional[str] = Query(None, description="AUTHENTIC / SUSPICIOUS / SMISHING / NOT_DISASTER"),
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


@app.delete("/messages/{message_id}", status_code=204)
async def delete_message(message_id: int):
    async with app.state.pool.acquire() as conn:
        result = await conn.execute("DELETE FROM incoming_messages WHERE message_id = $1", message_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="해당 message_id를 찾을 수 없습니다.")
    return Response(status_code=204)


class BulkDeleteRequest(BaseModel):
    message_ids: list[int] = Field(..., min_length=1, description="삭제할 message_id 목록")


@app.post("/messages/bulk-delete")
async def bulk_delete_messages(body: BulkDeleteRequest):
    """선택한 여러 건을 한 번에 삭제한다."""
    async with app.state.pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM incoming_messages WHERE message_id = ANY($1::int[])",
            body.message_ids,
        )
    deleted_count = int(result.split(" ")[-1]) if result.startswith("DELETE") else 0
    return {"deleted_count": deleted_count}


@app.delete("/messages")
async def delete_all_messages(device_id: Optional[str] = Query(None, description="지정하면 이 단말 것만 전체삭제")):
    """탐지 이력 전체 삭제. device_id를 주면 해당 단말 것만 지운다."""
    async with app.state.pool.acquire() as conn:
        if device_id:
            result = await conn.execute("DELETE FROM incoming_messages WHERE device_id = $1", device_id)
        else:
            result = await conn.execute("DELETE FROM incoming_messages")
    deleted_count = int(result.split(" ")[-1]) if result.startswith("DELETE") else 0
    return {"deleted_count": deleted_count}


@app.patch("/messages/{message_id}/report", status_code=204)
async def report_message(message_id: int):
    async with app.state.pool.acquire() as conn:
        result = await conn.execute("UPDATE incoming_messages SET reported = TRUE WHERE message_id = $1", message_id)
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="해당 message_id를 찾을 수 없습니다.")
    return Response(status_code=204)


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