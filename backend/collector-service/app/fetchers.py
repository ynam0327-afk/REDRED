"""
소방청(bigdata-119.kr) 3개 API + 행정안전부(safetydata.go.kr) 긴급재난문자 API를
호출하는 fetcher. 두 플랫폼은 인증 방식과 호출 방식이 서로 다르다.

  - bigdata-119.kr : POST, 인증은 X-API-KEY 헤더, 워터마크는 gtrRegDt(등재시각)
  - safetydata.go.kr: GET,  인증은 serviceKey 쿼리파라미터, 워터마크는 SN(일련번호)

두 플랫폼 모두 "매번 전체를 다시 받지 않고 새 레코드만 큐에 넣는다"는
증분 수집 원칙은 동일하게 따르되, 워터마크 비교 기준 필드만 다르게 처리한다.
"""

import asyncio
import json
import logging
from datetime import date
from typing import Any

import httpx
import redis.asyncio as redis

from .config import settings

logger = logging.getLogger(__name__)

WATERMARK_KEY_PREFIX = "redred:watermark:"

MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 2  # 1번째 실패 후 2초, 2번째 실패 후 4초 대기


async def _request_with_retry(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """
    일시적인 네트워크 오류(타임아웃, 연결 끊김)나 서버 5xx에 대해서만 지수 백오프로 재시도한다.
    4xx(인증키 오류, 잘못된 파라미터 등)는 재시도해도 결과가 똑같으므로 즉시 실패시킨다.
    """
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code < 500:
                raise  # 4xx는 재시도 무의미 -> 즉시 상위로 전파
            last_exc = e
        except httpx.TransportError as e:
            last_exc = e

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE_SECONDS ** attempt
            logger.warning("요청 실패(%s), %d초 후 %d번째 재시도: %s", url, wait, attempt + 1, last_exc)
            await asyncio.sleep(wait)

    assert last_exc is not None
    raise last_exc


# =======================================================================
# 1. bigdata-119.kr (call-receipts / fire-incidents / rescue-incidents)
# =======================================================================
BIGDATA119_BASE_URL = "http://www.bigdata-119.kr/fsdpApi/rest/v1"

BIGDATA119_DATASETS = [
    {"path": "call-receipts", "pk_field": "dclrRcptNo", "source_tag": "CALL_RECEIPT"},
    {"path": "fire-incidents", "pk_field": "wrinvNo", "source_tag": "FIRE"},
    {"path": "rescue-incidents", "pk_field": "clmtyRscuRptpNo", "source_tag": "RESCUE"},
]


async def push_to_stream(r: redis.Redis, source_tag: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    pipe = r.pipeline()
    for item in items:
        envelope = {"source_tag": source_tag, "payload": item}
        pipe.xadd(settings.redis_stream_key, {"data": json.dumps(envelope, ensure_ascii=False)})
    await pipe.execute()


async def fetch_one_bigdata119_dataset(client: httpx.AsyncClient, r: redis.Redis, dataset: dict) -> int:
    """한 데이터셋을 조회하고, gtrRegDt 기준 새 레코드만 Redis Stream에 push."""
    url = f"{BIGDATA119_BASE_URL}/{dataset['path']}"
    headers = {"X-API-KEY": settings.bigdata119_api_key}
    params = {"page": 1, "size": 100, "sort": "gtrRegDt,desc"}

    resp = await _request_with_retry(client, "POST", url, headers=headers, params=params, timeout=30.0)
    body = resp.json()
    items: list[dict[str, Any]] = body.get("items", [])

    watermark_key = f"{WATERMARK_KEY_PREFIX}{dataset['source_tag']}"
    last_watermark = await r.get(watermark_key)
    last_watermark = int(last_watermark) if last_watermark else 0

    new_items = [item for item in items if item.get("gtrRegDt", 0) > last_watermark]
    if not new_items:
        logger.info("[%s] 새 레코드 없음 (watermark=%s)", dataset["source_tag"], last_watermark)
        return 0

    await push_to_stream(r, dataset["source_tag"], new_items)

    max_watermark = max(item["gtrRegDt"] for item in new_items)
    await r.set(watermark_key, max_watermark)

    logger.info("[%s] 새 레코드 %d건 큐에 적재, watermark 갱신 -> %s",
                dataset["source_tag"], len(new_items), max_watermark)
    return len(new_items)


# =======================================================================
# 2. safetydata.go.kr 긴급재난문자 (DSSP-IF-00247)
# =======================================================================
SAFETYDATA_BASE_URL = "https://www.safetydata.go.kr/V2/api"
OFFICIAL_ALERT_ENDPOINT = f"{SAFETYDATA_BASE_URL}/DSSP-IF-00247"
OFFICIAL_ALERT_SOURCE_TAG = "OFFICIAL_ALERT"


async def fetch_official_alerts(client: httpx.AsyncClient, r: redis.Redis) -> int:
    """
    crtDt를 '오늘 날짜'로 매번 재조회하고, SN(일련번호) 워터마크로 새 레코드만 push한다.
    이 API는 gtrRegDt 같은 등재시각 필드가 없고 SN이 단조증가하는 일련번호이므로
    이를 워터마크로 사용한다.
    """
    today_str = date.today().strftime("%Y%m%d")
    params = {
        "serviceKey": settings.safetydata_api_key,
        "returnType": "json",
        "pageNo": 1,
        "numOfRows": 100,
        "crtDt": today_str,
    }

    resp = await _request_with_retry(client, "GET", OFFICIAL_ALERT_ENDPOINT, params=params, timeout=30.0)
    body = resp.json()
    items: list[dict[str, Any]] = body.get("body", [])

    watermark_key = f"{WATERMARK_KEY_PREFIX}{OFFICIAL_ALERT_SOURCE_TAG}"
    last_watermark = await r.get(watermark_key)
    last_watermark = int(last_watermark) if last_watermark else 0

    new_items = [item for item in items if item.get("SN", 0) > last_watermark]
    if not new_items:
        logger.info("[%s] 새 레코드 없음 (watermark=%s)", OFFICIAL_ALERT_SOURCE_TAG, last_watermark)
        return 0

    await push_to_stream(r, OFFICIAL_ALERT_SOURCE_TAG, new_items)

    max_watermark = max(item["SN"] for item in new_items)
    await r.set(watermark_key, max_watermark)

    logger.info("[%s] 새 레코드 %d건 큐에 적재, watermark 갱신 -> %s",
                OFFICIAL_ALERT_SOURCE_TAG, len(new_items), max_watermark)
    return len(new_items)


# =======================================================================
# 3. 전체 실행
# =======================================================================
async def fetch_all_datasets() -> None:
    r = redis.from_url(settings.redis_url, decode_responses=True)
    async with httpx.AsyncClient() as client:
        for dataset in BIGDATA119_DATASETS:
            try:
                await fetch_one_bigdata119_dataset(client, r, dataset)
            except httpx.HTTPStatusError as e:
                logger.error("[%s] API 호출 실패: %s", dataset["source_tag"], e)
            except Exception:
                logger.exception("[%s] 처리 중 예외 발생", dataset["source_tag"])

        try:
            await fetch_official_alerts(client, r)
        except httpx.HTTPStatusError as e:
            logger.error("[%s] API 호출 실패: %s", OFFICIAL_ALERT_SOURCE_TAG, e)
        except Exception:
            logger.exception("[%s] 처리 중 예외 발생", OFFICIAL_ALERT_SOURCE_TAG)

    await r.aclose()
