"""
notification-service(백엔드 단독 모듈) 부하 테스트 스크립트.

collector-service 이미지 안에서 실행한다 - httpx가 이미 설치돼 있어서 별도 설치가 필요 없다.
docker 내부 네트워크에서 notification-service에 직접 접속하므로, 실제 서비스에
영향을 주는 건 notification-service/postgres 뿐이다 (collector-service 자체 폴링과는 무관).

실행 방법:
    docker compose run --rm collector-service python -m app.loadtest

강도 조절(환경변수, 전부 선택):
    LOADTEST_TARGET_URL    기본: http://notification-service:8000
    LOADTEST_CONCURRENCY   기본: 20   (동시 요청 수)
    LOADTEST_DURATION_SEC  기본: 15   (시나리오 하나당 몇 초간 부하를 줄지)
"""

import asyncio
import os
import random
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

TARGET_URL = os.environ.get("LOADTEST_TARGET_URL", "http://notification-service:8000")
CONCURRENCY = int(os.environ.get("LOADTEST_CONCURRENCY", "20"))
DURATION_SEC = int(os.environ.get("LOADTEST_DURATION_SEC", "15"))


def random_message_body() -> dict:
    """POST /messages용 샘플 바디. matched_event_id는 일부러 생략 (FK 위반으로 400 나는 걸 피하기 위해)."""
    return {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "raw_text": f"부하테스트 샘플 문자 #{random.randint(1, 1_000_000)}",
        "url_risk_score": round(random.random(), 3),
        "text_authenticity_score": round(random.random(), 3),
    }


async def worker(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    json_body_fn: Optional[Callable[[], dict]],
    latencies: list[float],
    errors: list,
    stop_at: float,
) -> None:
    while time.monotonic() < stop_at:
        start = time.monotonic()
        try:
            if method == "GET":
                resp = await client.get(path, timeout=10.0)
            else:
                resp = await client.post(path, json=json_body_fn(), timeout=10.0)
            elapsed = time.monotonic() - start
            if resp.status_code >= 400:
                errors.append(resp.status_code)
            else:
                latencies.append(elapsed)
        except Exception as e:
            errors.append(repr(e))


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(len(sorted_values) * pct)))
    return sorted_values[idx]


async def run_scenario(name: str, method: str, path: str, json_body_fn: Optional[Callable[[], dict]] = None) -> None:
    latencies: list[float] = []
    errors: list = []

    async with httpx.AsyncClient(base_url=TARGET_URL) as client:
        stop_at = time.monotonic() + DURATION_SEC
        tasks = [
            asyncio.create_task(worker(client, method, path, json_body_fn, latencies, errors, stop_at))
            for _ in range(CONCURRENCY)
        ]
        await asyncio.gather(*tasks)

    total = len(latencies) + len(errors)
    print(f"\n=== {name} ({method} {path}) ===")
    print(f"동시 요청 수: {CONCURRENCY}, 테스트 시간: {DURATION_SEC}초")
    print(f"총 요청: {total}건 (성공 {len(latencies)} / 실패 {len(errors)})")

    if latencies:
        latencies.sort()
        print(f"처리량: {len(latencies) / DURATION_SEC:.1f} req/s")
        print(
            f"지연시간(ms) - p50: {_percentile(latencies, 0.50) * 1000:.1f} / "
            f"p95: {_percentile(latencies, 0.95) * 1000:.1f} / "
            f"p99: {_percentile(latencies, 0.99) * 1000:.1f} / "
            f"최대: {max(latencies) * 1000:.1f}"
        )
    if errors:
        print(f"에러 샘플(최대 5개): {errors[:5]}")


async def main() -> None:
    print(f"부하 테스트 대상: {TARGET_URL}")
    print(f"(동시 요청 {CONCURRENCY}개, 시나리오당 {DURATION_SEC}초)")

    await run_scenario("헬스체크", "GET", "/health")
    await run_scenario("이벤트 목록 조회 (/events)", "GET", "/events?limit=50")
    await run_scenario("메시지 목록 조회 (/messages)", "GET", "/messages?limit=50")
    await run_scenario("메시지 생성 (/messages, 쓰기)", "POST", "/messages", random_message_body)


if __name__ == "__main__":
    asyncio.run(main())
