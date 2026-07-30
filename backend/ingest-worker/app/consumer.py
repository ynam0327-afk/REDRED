"""
Redis Stream(fire_events_stream)을 Consumer Group으로 구독하여
normalized_events 테이블에 적재한다.

Consumer Group을 쓰는 이유: 워커를 여러 개(예: ingest-worker-1, -2)로 수평 확장해도
같은 메시지를 중복 처리하지 않도록 Redis가 분배해준다. (트래픽 폭주 시 워커 replica만 늘리면 됨)

주의: from_official_alert()만 유일하게 리스트를 반환한다 (긴급재난문자 지역 fan-out).
      나머지 세 소스는 단건(NormalizedEvent | None)을 반환한다.
      아래 handle_message는 두 경우를 모두 리스트로 정규화해서 동일하게 처리한다.
"""

import asyncio
import json
import logging

import asyncpg
import redis.asyncio as redis

from .config import settings
from .models import (
    NormalizedEvent,
    RawCallReceipt,
    RawFireIncident,
    RawOfficialAlert,
    RawRescueIncident,
    extract_agency_from_msg,
    from_call_receipt,
    from_fire_incident,
    from_official_alert,
    from_rescue_incident,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SOURCE_HANDLERS = {
    "CALL_RECEIPT": (RawCallReceipt, from_call_receipt),
    "FIRE": (RawFireIncident, from_fire_incident),
    "RESCUE": (RawRescueIncident, from_rescue_incident),
    "OFFICIAL_ALERT": (RawOfficialAlert, from_official_alert),
}

async def ensure_consumer_group(r: redis.Redis) -> None:
    try:
        await r.xgroup_create(settings.redis_stream_key, settings.consumer_group, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise  # 그룹이 이미 있으면 무시, 다른 에러면 재발생


async def upsert_raw_official_alert(conn: asyncpg.Connection, raw: RawOfficialAlert, raw_payload_json: str) -> None:
    """
    긴급재난문자 원본을 raw_official_alerts에 보존한다.
    normalized_events.summary_title은 MSG_CN을 40자로 잘라서 저장하므로,
    URL/기관명처럼 본문 뒷부분에 있는 정보는 이 raw 테이블에서만 온전히 확인할 수 있다.

    ON CONFLICT DO UPDATE를 쓰는 이유: 같은 SN에 대해 정정 문자가 재수신되는 경우를
    대비한 것. 다만 collector-service의 현재 워터마크 로직(SN > last_watermark)은
    이미 처리한 SN을 재조회하지 않으므로, 정정 반영이 실제로 필요하다면
    collector 쪽 폴링 전략도 함께 손봐야 한다 (지금은 raw 테이블 쪽만 안전하게 대비).
    """
    agency = extract_agency_from_msg(raw.MSG_CN)

    result = await conn.execute(
        """
        INSERT INTO raw_official_alerts (
            sn, crt_dt, msg_cn, rcptn_rgn_nm, emrg_step_nm, dst_se_nm, agency,
            reg_ymd, mdfcn_ymd, raw_payload
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
        ON CONFLICT (sn) DO UPDATE SET
            crt_dt = EXCLUDED.crt_dt,
            msg_cn = EXCLUDED.msg_cn,
            rcptn_rgn_nm = EXCLUDED.rcptn_rgn_nm,
            emrg_step_nm = EXCLUDED.emrg_step_nm,
            dst_se_nm = EXCLUDED.dst_se_nm,
            agency = EXCLUDED.agency,
            reg_ymd = EXCLUDED.reg_ymd,
            mdfcn_ymd = EXCLUDED.mdfcn_ymd,
            raw_payload = EXCLUDED.raw_payload
        """,
        raw.SN, raw.CRT_DT, raw.MSG_CN, raw.RCPTN_RGN_NM, raw.EMRG_STEP_NM, raw.DST_SE_NM, agency,
        raw.REG_YMD, raw.MDFCN_YMD, raw_payload_json,
    )
    logger.info("raw_official_alerts upsert 완료: sn=%s, agency=%r", raw.SN, agency)


async def upsert_raw_call_receipt(conn: asyncpg.Connection, raw: RawCallReceipt, raw_payload_json: str) -> None:
    """전국 119 신고접수 현황 원본 보존. PK: dclr_rcpt_no."""
    await conn.execute(
        """
        INSERT INTO raw_call_receipts (
            dclr_rcpt_no, dclr_dt, rcpt_end_dt, dspt_drtv_dt, grnds_arvl_dt, hsptl_arvl_dt, cbk_dt, sittn_end_dt,
            reporter_ctpv_nm, reporter_sgg_nm, reporter_emd_nm, reporter_lon, reporter_lat,
            disaster_ctpv_nm, disaster_sgg_nm, disaster_emd_nm, disaster_lon, disaster_lat,
            frstn_nm, cntr_nm, otr_ctpv_dclr_yn, raw_payload
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22::jsonb)
        ON CONFLICT (dclr_rcpt_no) DO UPDATE SET
            dclr_dt = EXCLUDED.dclr_dt, rcpt_end_dt = EXCLUDED.rcpt_end_dt, dspt_drtv_dt = EXCLUDED.dspt_drtv_dt,
            grnds_arvl_dt = EXCLUDED.grnds_arvl_dt, hsptl_arvl_dt = EXCLUDED.hsptl_arvl_dt, cbk_dt = EXCLUDED.cbk_dt,
            sittn_end_dt = EXCLUDED.sittn_end_dt,
            reporter_ctpv_nm = EXCLUDED.reporter_ctpv_nm, reporter_sgg_nm = EXCLUDED.reporter_sgg_nm,
            reporter_emd_nm = EXCLUDED.reporter_emd_nm, reporter_lon = EXCLUDED.reporter_lon, reporter_lat = EXCLUDED.reporter_lat,
            disaster_ctpv_nm = EXCLUDED.disaster_ctpv_nm, disaster_sgg_nm = EXCLUDED.disaster_sgg_nm,
            disaster_emd_nm = EXCLUDED.disaster_emd_nm, disaster_lon = EXCLUDED.disaster_lon, disaster_lat = EXCLUDED.disaster_lat,
            frstn_nm = EXCLUDED.frstn_nm, cntr_nm = EXCLUDED.cntr_nm, otr_ctpv_dclr_yn = EXCLUDED.otr_ctpv_dclr_yn,
            raw_payload = EXCLUDED.raw_payload
        """,
        raw.dclrRcptNo, raw.dclrDt, raw.rcptEndDt, raw.dsptDrtvDt, raw.grndsArvlDt, raw.hsptlArvlDt, raw.cbkDt, raw.sittnEndDt,
        raw.ctpvNm, raw.sggNm, raw.emdNm, raw.dclrPstnLot, raw.dclrPstnLat,
        raw.clmtyCtpvNm, raw.clmtySggNm, raw.clmtyEmdNm, raw.lot, raw.lat,
        raw.frstnNm, raw.cntrNm, raw.otrCtpvDclrYn, raw_payload_json,
    )
    logger.info("raw_call_receipts upsert 완료: dclr_rcpt_no=%s", raw.dclrRcptNo)


async def upsert_raw_fire_incident(conn: asyncpg.Connection, raw: RawFireIncident, raw_payload_json: str) -> None:
    """전국 화재 현황 원본 보존. PK: wrinv_no."""
    await conn.execute(
        """
        INSERT INTO raw_fire_incidents (
            wrinv_no, rcpt_dt, dspt_dt, grnds_arvl_dt, bgnn_potfr_dt, prfect_potfr_dt, cbk_dt,
            dspt_req_hr, fire_supesn_hr, ctpv_nm, sgg_nm, frstn_grnds_dstnc, cntr_grnds_dstnc,
            frstn_nm, cntr_nm, fire_type_nm, fclt_plc_lclsf_nm, fclt_plc_mclsf_nm, fclt_plc_sclsf_nm, spfptg_nm,
            dth_cnt, injpsn_cnt, hnl_dam_cnt, prpt_dam_amt, mub_yn, raw_payload
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26::jsonb)
        ON CONFLICT (wrinv_no) DO UPDATE SET
            rcpt_dt = EXCLUDED.rcpt_dt, dspt_dt = EXCLUDED.dspt_dt, grnds_arvl_dt = EXCLUDED.grnds_arvl_dt,
            bgnn_potfr_dt = EXCLUDED.bgnn_potfr_dt, prfect_potfr_dt = EXCLUDED.prfect_potfr_dt, cbk_dt = EXCLUDED.cbk_dt,
            dspt_req_hr = EXCLUDED.dspt_req_hr, fire_supesn_hr = EXCLUDED.fire_supesn_hr,
            ctpv_nm = EXCLUDED.ctpv_nm, sgg_nm = EXCLUDED.sgg_nm,
            frstn_grnds_dstnc = EXCLUDED.frstn_grnds_dstnc, cntr_grnds_dstnc = EXCLUDED.cntr_grnds_dstnc,
            frstn_nm = EXCLUDED.frstn_nm, cntr_nm = EXCLUDED.cntr_nm,
            fire_type_nm = EXCLUDED.fire_type_nm, fclt_plc_lclsf_nm = EXCLUDED.fclt_plc_lclsf_nm,
            fclt_plc_mclsf_nm = EXCLUDED.fclt_plc_mclsf_nm, fclt_plc_sclsf_nm = EXCLUDED.fclt_plc_sclsf_nm,
            spfptg_nm = EXCLUDED.spfptg_nm,
            dth_cnt = EXCLUDED.dth_cnt, injpsn_cnt = EXCLUDED.injpsn_cnt, hnl_dam_cnt = EXCLUDED.hnl_dam_cnt,
            prpt_dam_amt = EXCLUDED.prpt_dam_amt, mub_yn = EXCLUDED.mub_yn, raw_payload = EXCLUDED.raw_payload
        """,
        raw.wrinvNo, raw.rcptDt, raw.dsptDt, raw.grndsArvlDt, raw.bgnnPotfrDt, raw.prfectPotfrDt, raw.cbkDt,
        raw.dsptReqHr, raw.fireSupesnHr, raw.ctpvNm, raw.sggNm, raw.frstnGrndsDstnc, raw.cntrGrndsDstnc,
        raw.frstnNm, raw.cntrNm, raw.fireTypeNm, raw.fcltPlcLclsfNm, raw.fcltPlcMclsfNm, raw.fcltPlcSclsfNm, raw.spfptgNm,
        raw.dthCnt, raw.injpsnCnt, raw.hnlDamCnt, raw.prptDamAmt, raw.mubYn, raw_payload_json,
    )
    logger.info("raw_fire_incidents upsert 완료: wrinv_no=%s", raw.wrinvNo)


async def upsert_raw_rescue_incident(conn: asyncpg.Connection, raw: RawRescueIncident, raw_payload_json: str) -> None:
    """전국 구조 현황 원본 보존. PK: clmty_rscu_rptp_no."""
    await conn.execute(
        """
        INSERT INTO raw_rescue_incidents (
            clmty_rscu_rptp_no, dclr_ymd, dclr_tm, dspt_ymd, dspt_tm, grnds_arvl_ymd, grnds_arvl_tm,
            rscu_cmptn_ymd, rscu_cmptn_tm, cbk_ymd, cbk_tm,
            ctpv_nm, sgg_nm, emd_nm, lon, lat,
            frstn_nm, cntr_nm, acdnt_cs_nm, acdnt_plc_dtl_nm, prcs_rslt_se_nm, raw_payload
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22::jsonb)
        ON CONFLICT (clmty_rscu_rptp_no) DO UPDATE SET
            dclr_ymd = EXCLUDED.dclr_ymd, dclr_tm = EXCLUDED.dclr_tm, dspt_ymd = EXCLUDED.dspt_ymd, dspt_tm = EXCLUDED.dspt_tm,
            grnds_arvl_ymd = EXCLUDED.grnds_arvl_ymd, grnds_arvl_tm = EXCLUDED.grnds_arvl_tm,
            rscu_cmptn_ymd = EXCLUDED.rscu_cmptn_ymd, rscu_cmptn_tm = EXCLUDED.rscu_cmptn_tm,
            cbk_ymd = EXCLUDED.cbk_ymd, cbk_tm = EXCLUDED.cbk_tm,
            ctpv_nm = EXCLUDED.ctpv_nm, sgg_nm = EXCLUDED.sgg_nm, emd_nm = EXCLUDED.emd_nm,
            lon = EXCLUDED.lon, lat = EXCLUDED.lat,
            frstn_nm = EXCLUDED.frstn_nm, cntr_nm = EXCLUDED.cntr_nm,
            acdnt_cs_nm = EXCLUDED.acdnt_cs_nm, acdnt_plc_dtl_nm = EXCLUDED.acdnt_plc_dtl_nm,
            prcs_rslt_se_nm = EXCLUDED.prcs_rslt_se_nm, raw_payload = EXCLUDED.raw_payload
        """,
        raw.clmtyRscuRptpNo, raw.dclrYmd, raw.dclrTm, raw.dsptYmd, raw.dsptTm, raw.grndsArvlYmd, raw.grndsArvlTm,
        raw.rscuCmptnYmd, raw.rscuCmptnTm, raw.cbkYmd, raw.cbkTm,
        raw.ctpvNm, raw.sggNm, raw.emdNm, raw.dclrPstnLot, raw.dclrPstnLat,
        raw.frstnNm, raw.cntrNm, raw.acdntCsNm, raw.acdntPlcDtlNm, raw.prcsRsltSeNm, raw_payload_json,
    )
    logger.info("raw_rescue_incidents upsert 완료: clmty_rscu_rptp_no=%s", raw.clmtyRscuRptpNo)


# source_tag별 raw_* upsert 함수 디스패치. handle_message에서 소스 종류에 상관없이
# 동일한 방식으로 호출하기 위함 (OFFICIAL_ALERT만 특별 취급하던 기존 if문을 일반화).
RAW_UPSERT_HANDLERS = {
    "CALL_RECEIPT": upsert_raw_call_receipt,
    "FIRE": upsert_raw_fire_incident,
    "RESCUE": upsert_raw_rescue_incident,
    "OFFICIAL_ALERT": upsert_raw_official_alert,
}


async def insert_event(conn: asyncpg.Connection, event: NormalizedEvent) -> None:
    await conn.execute(
        """
        INSERT INTO normalized_events (
            event_id, incident_type, source_pk, occurred_at,
            sido_nm, sigungu_nm, eupmyeondong_nm, lon, lat,
            location_precision, summary_title, severity_hint
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (event_id) DO NOTHING
        """,
        event.event_id, event.incident_type.value, event.source_pk, event.occurred_at,
        event.sido_nm, event.sigungu_nm, event.eupmyeondong_nm, event.lon, event.lat,
        event.location_precision.value, event.summary_title, event.severity_hint,
    )


DEAD_LETTER_KEY = "redred:deadletter"
PENDING_MIN_IDLE_MS = 30_000   # 이만큼 오래 ACK 안 된(예: 워커가 죽어서 못 끝낸) 메시지만 회수 대상
PENDING_CLAIM_BATCH = 20
MAX_DELIVERY_COUNT = 5         # 이 횟수 넘게 재시도해도 계속 실패하면 poison message로 간주


async def reclaim_pending_messages(r: redis.Redis, pool: asyncpg.Pool) -> None:
    """
    죽은 워커(재시작 전 인스턴스 등)가 ACK하지 못하고 들고 있던 pending 메시지를 회수해서
    재처리한다. 지금까지는 실패한 메시지가 ACK도 안 되고 재시도도 안 된 채 PEL(Pending
    Entries List)에 영원히 쌓이기만 했는데, 이 함수가 주기적으로 그걸 확인해서 처리한다.

    MAX_DELIVERY_COUNT를 넘기면 그 메시지는 "계속 실패하는 메시지(poison message)"로 보고,
    dead-letter 리스트에 원본을 보존한 뒤 ACK로 큐에서 빼낸다. 그렇지 않으면 이 메시지 하나
    때문에 뒤에 쌓인 정상 메시지들까지 영원히 처리가 막히는 상황이 생길 수 있다.
    """
    try:
        pending = await r.xpending_range(
            settings.redis_stream_key, settings.consumer_group,
            min="-", max="+", count=PENDING_CLAIM_BATCH, idle=PENDING_MIN_IDLE_MS,
        )
    except redis.ResponseError:
        return  # 스트림/그룹이 아직 없는 초기 상태 -> 조용히 스킵

    for entry in pending:
        message_id = entry["message_id"]
        delivery_count = entry["times_delivered"]

        claimed = await r.xclaim(
            settings.redis_stream_key, settings.consumer_group, settings.consumer_name,
            min_idle_time=PENDING_MIN_IDLE_MS, message_ids=[message_id],
        )
        if not claimed:
            continue  # 그 사이 다른 컨슈머가 먼저 ACK했을 수 있음

        for claimed_id, fields in claimed:
            if delivery_count > MAX_DELIVERY_COUNT:
                await r.rpush(DEAD_LETTER_KEY, fields.get("data", "{}"))
                await r.xack(settings.redis_stream_key, settings.consumer_group, claimed_id)
                logger.error(
                    "[dead-letter] message_id=%s 재시도 %d회 초과 -> 격리 후 ACK (내용은 %s에 보존)",
                    claimed_id, delivery_count, DEAD_LETTER_KEY,
                )
                continue

            try:
                envelope = json.loads(fields["data"])
                await handle_message(pool, envelope)
                await r.xack(settings.redis_stream_key, settings.consumer_group, claimed_id)
                logger.info("pending 메시지 재처리 성공: message_id=%s (재시도 %d회째)", claimed_id, delivery_count)
            except Exception:
                logger.exception("pending 메시지 재처리 실패 (message_id=%s, %d회째 시도) - 다음 회수 때 재시도",
                                  claimed_id, delivery_count)


async def handle_message(pool: asyncpg.Pool, envelope: dict) -> None:
    source_tag = envelope["source_tag"]
    payload = envelope["payload"]

    raw_model_cls, normalize_fn = SOURCE_HANDLERS[source_tag]
    raw = raw_model_cls(**payload)
    result = normalize_fn(raw)

    # from_official_alert()만 list를 반환하고 나머지는 단건(또는 None) -> 리스트로 통일
    events: list[NormalizedEvent]
    if result is None:
        events = []
    elif isinstance(result, list):
        events = result
    else:
        events = [result]

    async with pool.acquire() as conn:
        async with conn.transaction():
            # raw 보존은 normalized 변환 성공 여부와 무관하게 항상 수행한다.
            # (occurred_at 파싱 실패로 events가 비어도 원본은 남겨서 재처리 가능하게)
            raw_payload_json = json.dumps(payload, ensure_ascii=False)
            upsert_fn = RAW_UPSERT_HANDLERS[source_tag]
            await upsert_fn(conn, raw, raw_payload_json)

            for event in events:
                await insert_event(conn, event)

    if not events:
        logger.warning("[%s] 정규화 결과 없음(occurred_at 파싱 실패 등), raw만 보존: payload=%s", source_tag, payload)
        return

    logger.info("[%s] 적재 완료 %d건 (예: %s)", source_tag, len(events), events[0].event_id)


async def run_consumer() -> None:
    r = redis.from_url(settings.redis_url, decode_responses=True)
    pool = await asyncpg.create_pool(dsn=settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))

    await ensure_consumer_group(r)
    logger.info("ingest-worker 시작. stream=%s group=%s", settings.redis_stream_key, settings.consumer_group)

    while True:
        try:
            resp = await r.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams={settings.redis_stream_key: ">"},
                count=20,
                block=5000,
            )
            if resp:
                for _stream_name, messages in resp:
                    for message_id, fields in messages:
                        try:
                            envelope = json.loads(fields["data"])
                            await handle_message(pool, envelope)
                            await r.xack(settings.redis_stream_key, settings.consumer_group, message_id)
                        except Exception:
                            logger.exception("메시지 처리 실패 (message_id=%s), ACK 보류 -> 재시도 대상", message_id)

            # 새 메시지 유무와 무관하게 매 사이클 오래된 pending 메시지도 회수 시도
            # (죽은 워커가 들고 있던 메시지가 영원히 안 풀리는 것을 방지)
            await reclaim_pending_messages(r, pool)
        except Exception:
            logger.exception("컨슈머 루프 예외, 5초 후 재시도")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_consumer())
