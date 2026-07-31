"""
FCM 실시간 푸시 발송.

중요: 이 스케줄러는 config.py의 enable_push_scheduler=True인 인스턴스에서만 켜진다.
notification-service가 여러 환경(백엔드 로컬 Docker, 팀원 로컬 네이티브 실행 등)에서
동시에 떠 있을 수 있는데, 전부 이 스케줄러를 켜두면 같은 이벤트에 대해 같은 사용자에게
중복 푸시가 나갈 위험이 있다. 그래서 기본은 꺼져 있고, 발송을 실제로 담당할 단 하나의
인스턴스(.env에서 명시적으로 켠 곳)에서만 동작한다.

MVP 범위: 지역 구독 없이 등록된 토큰 전체에 브로드캐스트한다.
"""

import logging

import asyncpg
import firebase_admin
from firebase_admin import credentials, messaging

from .config import settings

logger = logging.getLogger(__name__)

_firebase_app = None


def init_firebase() -> None:
    """Firebase Admin SDK 초기화. 서비스 계정 키 파일이 없으면 여기서 바로 예외가 난다
    (스케줄러를 켰는데 키가 없는 상태로 조용히 넘어가지 않도록 일부러 그렇게 뒀다)."""
    global _firebase_app
    if _firebase_app is not None:
        return
    cred = credentials.Certificate(settings.fcm_service_account_json_path)
    _firebase_app = firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK 초기화 완료")


async def send_pending_notifications(pool: asyncpg.Pool) -> None:
    """
    normalized_events에서 아직 안 보낸(is_notified=FALSE) 이벤트를 찾아 등록된 토큰
    전체에 발송하고, 발송 성공 시 is_notified=TRUE로 갱신한다.
    발송 자체가 실패하면(네트워크 오류 등) is_notified를 갱신하지 않아 다음 주기에 재시도된다.
    """
    async with pool.acquire() as conn:
        events = await conn.fetch(
            """
            SELECT event_id, summary_title, severity_hint, sido_nm, sigungu_nm
            FROM normalized_events
            WHERE is_notified = FALSE
            ORDER BY occurred_at ASC
            LIMIT 50
            """
        )
        if not events:
            return

        token_rows = await conn.fetch("SELECT token FROM device_tokens")
        tokens = [r["token"] for r in token_rows]

        if not tokens:
            logger.info("등록된 단말 토큰이 없어 푸시를 건너뜀 (미발송 이벤트 %d건 대기 중)", len(events))
            return

        for event in events:
            region = " ".join(filter(None, [event["sido_nm"], event["sigungu_nm"]]))
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=f"[{event['severity_hint'] or '안전안내'}] {region}".strip(),
                    body=event["summary_title"] or "",
                ),
                tokens=tokens,
            )

            try:
                response = messaging.send_each_for_multicast(message)
            except Exception:
                logger.exception("푸시 발송 실패(다음 주기에 재시도): event_id=%s", event["event_id"])
                continue

            logger.info(
                "푸시 발송 완료: event_id=%s 성공 %d / 실패 %d",
                event["event_id"], response.success_count, response.failure_count,
            )

            # 더 이상 유효하지 않은 토큰(앱 삭제 등)은 정리해서 다음부터 헛발송하지 않게 함
            if response.failure_count > 0:
                invalid_tokens = [
                    tokens[idx]
                    for idx, resp in enumerate(response.responses)
                    if not resp.success and isinstance(resp.exception, messaging.UnregisteredError)
                ]
                if invalid_tokens:
                    await conn.execute("DELETE FROM device_tokens WHERE token = ANY($1::text[])", invalid_tokens)
                    logger.info("만료된 단말 토큰 %d개 정리", len(invalid_tokens))

            await conn.execute(
                "UPDATE normalized_events SET is_notified = TRUE WHERE event_id = $1", event["event_id"]
            )
