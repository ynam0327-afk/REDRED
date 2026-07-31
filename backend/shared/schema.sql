-- =====================================================================
-- RedRed 프로젝트 최종 스키마 (v2)
--
-- 데이터 소스 4종:
--   1. bigdata-119.kr call-receipts     (전국 119 신고접수 현황)
--   2. bigdata-119.kr fire-incidents    (전국 화재 현황)
--   3. bigdata-119.kr rescue-incidents  (전국 구조 현황)
--   4. safetydata.go.kr DSSP-IF-00247   (행정안전부 긴급재난문자)
--
-- 설계 원칙 :
--   - raw_* 테이블은 원본 응답 구조를 보존한다 (스펙 변경 시 재처리 가능하도록)
--   - normalized_events 하나만 알림 서비스가 조회한다 (소스별 위치 정밀도 차이를 흡수)
--   - 화재는 좌표가 없어 SIGUNGU 정밀도가 상한이다
--   - 긴급재난문자는 하나의 원본이 여러 지역에 걸칠 수 있어 지역별로 fan-out 하여 저장한다
--     -> 따라서 normalized_events는 (incident_type, source_pk) 유니크가 아니라
--        event_id 자체가 전역 유일키다
--   - 구급(구급현황) 데이터는 의도적으로 포함하지 않는다 (개인 의료정보 성격, 알림 실익 낮음)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. RAW: 신고접수현황 (call-receipts)
-- PK: dclrRcptNo | 위치: 신고자 위치 / 재난 위치가 분리되어 제공됨
-- ---------------------------------------------------------------------
CREATE TABLE raw_call_receipts (
    dclr_rcpt_no          VARCHAR(20)  PRIMARY KEY,

    dclr_dt               VARCHAR(14), -- 신고일시
    rcpt_end_dt            VARCHAR(14),
    dspt_drtv_dt           VARCHAR(14),
    grnds_arvl_dt          VARCHAR(14),
    hsptl_arvl_dt          VARCHAR(14),
    cbk_dt                 VARCHAR(14),
    sittn_end_dt           VARCHAR(14),

    reporter_ctpv_nm       VARCHAR(20),
    reporter_sgg_nm        VARCHAR(20),
    reporter_emd_nm        VARCHAR(20),
    reporter_lon           NUMERIC(13,10),
    reporter_lat           NUMERIC(12,10),

    disaster_ctpv_nm       VARCHAR(20),
    disaster_sgg_nm        VARCHAR(20),
    disaster_emd_nm        VARCHAR(20),
    disaster_lon           NUMERIC(13,10), -- 결측 비율 매우 높음(관측상 약 80%)
    disaster_lat           NUMERIC(12,10),

    frstn_nm                VARCHAR(200),
    cntr_nm                 VARCHAR(100),
    otr_ctpv_dclr_yn        CHAR(1),

    ingested_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload              JSONB
);

CREATE INDEX idx_rcr_disaster_region ON raw_call_receipts (disaster_ctpv_nm, disaster_sgg_nm, disaster_emd_nm);
CREATE INDEX idx_rcr_dclr_dt ON raw_call_receipts (dclr_dt);


-- ---------------------------------------------------------------------
-- 2. RAW: 화재현황 (fire-incidents)
-- PK: wrinvNo (접수 시점부터 채워짐, 확인 완료) | 위치: 좌표 없음, 시군구가 최고 정밀도
-- ---------------------------------------------------------------------
CREATE TABLE raw_fire_incidents (
    wrinv_no                VARCHAR(25) PRIMARY KEY,

    rcpt_dt                 VARCHAR(14),
    dspt_dt                 VARCHAR(14),
    grnds_arvl_dt            VARCHAR(14),
    bgnn_potfr_dt             VARCHAR(14),
    prfect_potfr_dt           VARCHAR(14),
    cbk_dt                  VARCHAR(14),
    dspt_req_hr              NUMERIC(7,0),
    fire_supesn_hr            NUMERIC(7,0),

    ctpv_nm                 VARCHAR(40),
    sgg_nm                  VARCHAR(40), -- 좌표 없음: 위치 정밀도 상한
    frstn_grnds_dstnc         NUMERIC(10,3),
    cntr_grnds_dstnc          NUMERIC(8,3),

    frstn_nm                 VARCHAR(200),
    cntr_nm                  VARCHAR(100),

    fire_type_nm              VARCHAR(20),
    fclt_plc_lclsf_nm          VARCHAR(20),
    fclt_plc_mclsf_nm          VARCHAR(20),
    fclt_plc_sclsf_nm          VARCHAR(100),
    spfptg_nm                 VARCHAR(20),

    dth_cnt                  NUMERIC(4,0)  DEFAULT 0,
    injpsn_cnt                NUMERIC(10,0) DEFAULT 0,
    hnl_dam_cnt                NUMERIC(7,0)  DEFAULT 0,
    prpt_dam_amt               NUMERIC(22,2),
    mub_yn                   CHAR(1),

    ingested_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload                JSONB
);

CREATE INDEX idx_rfi_region ON raw_fire_incidents (ctpv_nm, sgg_nm);
CREATE INDEX idx_rfi_dspt_dt ON raw_fire_incidents (dspt_dt);


-- ---------------------------------------------------------------------
-- 3. RAW: 구조현황 (rescue-incidents)
-- PK: clmtyRscuRptpNo | 위치: 단일 세트(신고=현장), 읍면동+좌표 보유
-- ---------------------------------------------------------------------
CREATE TABLE raw_rescue_incidents (
    clmty_rscu_rptp_no        VARCHAR(20) PRIMARY KEY,

    dclr_ymd                 VARCHAR(8),
    dclr_tm                  VARCHAR(6),
    dspt_ymd                 VARCHAR(8),
    dspt_tm                  VARCHAR(6),
    grnds_arvl_ymd             VARCHAR(8),
    grnds_arvl_tm              VARCHAR(6),
    rscu_cmptn_ymd             VARCHAR(8),
    rscu_cmptn_tm              VARCHAR(6),
    cbk_ymd                  VARCHAR(8),
    cbk_tm                   VARCHAR(6),

    ctpv_nm                  VARCHAR(40),
    sgg_nm                   VARCHAR(40),
    emd_nm                   VARCHAR(40),
    lon                      NUMERIC(13,10),
    lat                      NUMERIC(12,10),

    frstn_nm                  VARCHAR(200),
    cntr_nm                   VARCHAR(100),

    acdnt_cs_nm                VARCHAR(20),
    acdnt_plc_dtl_nm             VARCHAR(40),
    prcs_rslt_se_nm              VARCHAR(20),

    ingested_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload                 JSONB
);

CREATE INDEX idx_rri_region ON raw_rescue_incidents (ctpv_nm, sgg_nm, emd_nm);
CREATE INDEX idx_rri_dclr ON raw_rescue_incidents (dclr_ymd, dclr_tm);


-- ---------------------------------------------------------------------
-- 4. RAW: 긴급재난문자 (safetydata.go.kr DSSP-IF-00247)
-- PK: SN | 위치: RCPTN_RGN_NM 하나에 여러 지역이 콤마로 나열 (원본은 펼치지 않고 그대로 보관)
-- 이 테이블만 유일하게 필수여부가 전부 'Y'로 명세되어 있어 NULL 우려가 적다.
-- ---------------------------------------------------------------------
CREATE TABLE raw_official_alerts (
    sn                       BIGINT       PRIMARY KEY,           -- SN

    crt_dt                   VARCHAR(20)  NOT NULL, -- 'YYYY/MM/DD HH:MM:SS'
    msg_cn                   VARCHAR(4000) NOT NULL, -- 재난문자 본문
    rcptn_rgn_nm               VARCHAR(4000) NOT NULL, -- 콤마 구분 지역 원문 (정규화는 normalized_events에서)
    emrg_step_nm               VARCHAR(100), -- 안전안내 / 주의 / 경계 / 심각
    dst_se_nm                 VARCHAR(100), -- 재해구분 (폭염/호우/기타 등)
    agency                   VARCHAR(100), -- 발신기관명. API 필드 아님 - msg_cn 끝의 [기관명] 표기를 정규식으로 추출 (shared/models.py의 extract_agency_from_msg)

    reg_ymd                   VARCHAR(50),
    mdfcn_ymd                 VARCHAR(50),

    ingested_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_payload                 JSONB
);

CREATE INDEX idx_roa_crt_dt ON raw_official_alerts (crt_dt);
CREATE INDEX idx_roa_agency ON raw_official_alerts (agency);

-- 이미 raw_official_alerts가 존재하는 환경(스키마를 처음부터 다시 안 돌리는 경우)에서는
-- 아래 ALTER를 대신 실행해서 컬럼만 추가할 것:
-- ALTER TABLE raw_official_alerts ADD COLUMN IF NOT EXISTS agency VARCHAR(100);
-- CREATE INDEX IF NOT EXISTS idx_roa_agency ON raw_official_alerts (agency);



-- =====================================================================
-- 5. NORMALIZED: 알림 서비스가 실제로 조회하는 통합 테이블
--
-- incident_type별 위치 정밀도 요약:
--   FIRE           -> 항상 SIGUNGU (원본에 좌표/읍면동 필드 자체가 없음)
--   RESCUE         -> COORDINATE 또는 EUPMYEONDONG (좌표 결측 시 후자)
--   CALL_RECEIPT   -> COORDINATE 또는 EUPMYEONDONG (재난 발생지 좌표 결측 비율 높음, 약 80%)
--   OFFICIAL_ALERT -> SIGUNGU 또는 EUPMYEONDONG (좌표 없음, 원문 지역명 파싱 결과에 따름)
--
-- source_pk가 유일하지 않을 수 있다 (긴급재난문자 fan-out으로 같은 SN이 여러 행에 반복).
-- 따라서 유니크 제약은 event_id(PK) 하나에만 걸고, (incident_type, source_pk)는
-- 일반 인덱스로만 두어 "원본 한 건이 몇 개 지역으로 갈라졌는지" 조회에 활용한다.
-- =====================================================================
CREATE TYPE incident_type_enum AS ENUM ('FIRE', 'RESCUE', 'CALL_RECEIPT', 'OFFICIAL_ALERT');
CREATE TYPE location_precision_enum AS ENUM ('COORDINATE', 'EUPMYEONDONG', 'SIGUNGU');

CREATE TABLE normalized_events (
    event_id                 VARCHAR(50)  PRIMARY KEY,
    -- 형식 예:
    --   'FIRE:240210010842471'
    --   'RESCUE:XP1234567890'
    --   'CALL_RECEIPT:XP1234567890'
    --   'OFFICIAL_ALERT:261240:0'   (SN:지역인덱스, fan-out 결과)

    incident_type             incident_type_enum NOT NULL,
    source_pk                 VARCHAR(25)  NOT NULL, -- raw_* 테이블 조인용 (유일하지 않을 수 있음)

    occurred_at                TIMESTAMP    NOT NULL,

    sido_nm                   VARCHAR(40),
    sigungu_nm                 VARCHAR(40),
    eupmyeondong_nm             VARCHAR(40),
    lon                       NUMERIC(13,10),
    lat                       NUMERIC(12,10),
    location_precision          location_precision_enum NOT NULL,

    summary_title              VARCHAR(200),
    severity_hint               VARCHAR(20), -- NORMAL / CAUTION / WARNING / CRITICAL / CASUALTY

    is_notified                BOOLEAN      DEFAULT FALSE,
    created_at                 TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ne_source_lookup ON normalized_events (incident_type, source_pk);
CREATE INDEX idx_ne_notify_queue ON normalized_events (is_notified, occurred_at) WHERE is_notified = FALSE;
CREATE INDEX idx_ne_region ON normalized_events (sido_nm, sigungu_nm, eupmyeondong_nm);
-- 필터 없이 '최신 N건' 조회(홈 화면에서 가장 흔한 패턴)가 부하테스트에서 유독 느렸던 원인.
-- ORDER BY occurred_at DESC만 있고 이 컬럼에 인덱스가 없어 매번 시퀀셜 스캔 + 정렬이 발생했다.
CREATE INDEX idx_ne_occurred_at ON normalized_events (occurred_at DESC);
-- PostGIS 확장을 쓴다면 좌표 반경 검색용 GIST 인덱스도 추가 권장:
-- CREATE INDEX idx_ne_geo ON normalized_events USING GIST (ST_MakePoint(lon, lat)) WHERE lon IS NOT NULL;


-- =====================================================================
-- 6. INCOMING_MESSAGES: 사용자 단말이 수신한 문자(스미싱 판별 대상)
--
-- 팀원이 만드는 두 모델(악성 URL 분류, 재난문자 진위 분류)의 출력을 받아
-- 하나의 smishing_score로 합치는 지점. 두 모델 자체는 이 서비스 밖에서
-- 돌고, 이 테이블/API는 그 결과를 받아 저장·조회하는 역할만 한다.
--
-- matched_event_id는 normalized_events(공식 검증 DB)에서 매칭된 사건이
-- 있으면 채워진다 (없으면 NULL -> 공식 DB에 없는, 즉 더 의심스러운 문자).
--
-- url_risk_score / text_authenticity_score의 가중치·임계값은 초기값이며,
-- 팀원 모델 성능이 나오는 대로 재조정 예정.
-- =====================================================================
CREATE TYPE smishing_verdict_enum AS ENUM ('AUTHENTIC', 'SUSPICIOUS', 'SMISHING');

CREATE TABLE incoming_messages (
    message_id                 BIGSERIAL PRIMARY KEY,

    received_at                 TIMESTAMP    NOT NULL, -- 사용자 단말이 문자를 수신한 시각(클라이언트 제공)
    raw_text                    VARCHAR(4000) NOT NULL, -- 수신 문자 원문

    detected_urls                JSONB, -- 팀원 URL 추출 모델 결과 (문자열 배열)
    url_risk_score                NUMERIC(4,3), -- 0~1, 팀원 악성 URL 모델 출력
    text_authenticity_score        NUMERIC(4,3), -- 0~1, 팀원 재난문자 분류 모델 출력 (공식 문체/패턴과의 유사도, 높을수록 진짜에 가까움)

    matched_sido_nm               VARCHAR(40), -- 문자 본문에서 추출된 지역 (팀원 파싱 결과)
    matched_sigungu_nm             VARCHAR(40),
    matched_event_id              VARCHAR(50) REFERENCES normalized_events(event_id),  -- 공식 DB 매칭 사건 (없으면 NULL)

    smishing_score                NUMERIC(4,3) NOT NULL, -- 최종 가중합 스코어 (0~1, 높을수록 위험)
    verdict                      smishing_verdict_enum NOT NULL,

    device_id                    VARCHAR(100), -- 클라이언트(단말) 식별용, 선택
    created_at                    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_im_created_at ON incoming_messages (created_at DESC);
CREATE INDEX idx_im_verdict ON incoming_messages (verdict);
CREATE INDEX idx_im_matched_event ON incoming_messages (matched_event_id);
CREATE INDEX idx_im_device ON incoming_messages (device_id);

-- =====================================================================
-- 7. DEVICE_TOKENS: FCM 푸시 발송 대상 단말 토큰
--
-- 지금은 MVP라 지역 구독 없이 등록된 토큰 전체에 브로드캐스트한다.
-- 나중에 "내 동네만 받기"를 만들게 되면 subscribed_sido_nm 같은 컬럼을
-- 추가하고 발송 로직에서 필터링하면 된다 (지금은 컬럼 자체가 없음).
-- =====================================================================
CREATE TABLE device_tokens (
    token           VARCHAR(255) PRIMARY KEY, -- FCM이 단말/앱 설치 단위로 발급하는 토큰
    device_id       VARCHAR(100), -- incoming_messages.device_id와 동일 개념(선택, 연결용)
    platform        VARCHAR(20), -- android / ios / web 등 (선택)
    registered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dt_device_id ON device_tokens (device_id);
