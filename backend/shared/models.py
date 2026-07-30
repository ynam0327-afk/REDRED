"""
RedRed 프로젝트 데이터 모델 (최종본 v2)

데이터 소스 4종:
    1. bigdata-119.kr call-receipts     (전국 119 신고접수 현황)
    2. bigdata-119.kr fire-incidents    (전국 화재 현황)
    3. bigdata-119.kr rescue-incidents  (전국 구조 현황)
    4. safetydata.go.kr DSSP-IF-00247   (행정안전부 긴급재난문자)

구조:
    1. 공통 유틸       : 날짜/좌표 파싱 헬퍼
    2. Raw* 모델        : 각 API 원본 응답을 그대로 매핑 (필드명은 원본 그대로 유지)
    3. NormalizedEvent  : 알림 서비스가 실제로 사용하는 통합 이벤트 모델
    4. from_*()         : 각 Raw 모델 -> NormalizedEvent 변환 함수
       (from_official_alert만 유일하게 리스트를 반환한다. 지역 fan-out 때문)
"""

from datetime import datetime
from enum import Enum
import re
from typing import Optional

from pydantic import BaseModel, field_validator


# =======================================================================
# 1. 공통 유틸
# =======================================================================
def parse_yyyymmddhhmmss(raw: Optional[str]) -> Optional[datetime]:
    """'20240210002340' 형태(공백 패딩 포함 가능)를 datetime으로 변환. 실패 시 None."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def parse_ymd_tm(ymd: Optional[str], tm: Optional[str]) -> Optional[datetime]:
    """구조현황처럼 'YYYYMMDD' + 'HHMMSS'로 분리된 필드를 합쳐서 파싱."""
    if not ymd or not tm:
        return None
    combined = ymd.strip() + tm.strip().zfill(6)
    return parse_yyyymmddhhmmss(combined)


def parse_slash_datetime(raw: Optional[str]) -> Optional[datetime]:
    """긴급재난문자의 '2026/07/17 07:59:01' 형태를 datetime으로 변환."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return None


def zero_to_none(v: Optional[float]) -> Optional[float]:
    """0 또는 0에 매우 가까운 값(관측된 '0E-10' 등)은 결측치로 취급."""
    if v is not None and abs(v) < 1e-6:
        return None
    return v


# "구"를 가진 시 목록 (2026-07 기준, 임시 하드코딩).
# 법정동 API(DSSP-IF-10072) 승인 후에는 이 목록을 참조 테이블 조회로 교체할 것.
# 출처: 각 시 홈페이지 기준 확인 필요 -> 승인 전까지는 알려진 주요 사례만 반영한 잠정 목록.
CITIES_WITH_DISTRICTS = {
    "수원시", "성남시", "안양시", "안산시", "고양시", "용인시",
    "청주시", "천안시", "전주시", "포항시", "창원시", "부천시",
}


def parse_region_string(region: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    '인천광역시 영종구 중산동' -> (시도, 시군구, 읍면동)
    '경기도 가평군'          -> (시도, 시군구, None)
    '경상북도 포항시 남구'    -> (시도, 시군구='포항시 남구', None)  <- CITIES_WITH_DISTRICTS로 보정

    임시 조치: 법정동 API(DSSP-IF-10072) 미승인 상태라 CITIES_WITH_DISTRICTS를
    하드코딩된 화이트리스트로 우선 방어한다. 승인되면 이 목록을 참조 테이블
    조회로 교체하여 전국 단위로 정확하게 만들 것 (지금은 알려진 사례만 커버).
    """
    tokens = region.strip().split()
    if not tokens:
        return None, None, None

    sido = tokens[0]

    if len(tokens) >= 3 and tokens[1] in CITIES_WITH_DISTRICTS:
        # '포항시 남구'처럼 시+구를 합쳐 하나의 시군구로 취급
        sigungu = f"{tokens[1]} {tokens[2]}"
        eupmyeondong = tokens[3] if len(tokens) >= 4 else None
        return sido, sigungu, eupmyeondong

    sigungu = tokens[1] if len(tokens) >= 2 else None
    eupmyeondong = tokens[2] if len(tokens) >= 3 else None
    return sido, sigungu, eupmyeondong


# 시도 약칭 -> 정식명칭 매핑 (2026-07 기준 행정구역 정식명칭).
# raw_official_alerts(RCPTN_RGN_NM)는 정식명칭 위주로 오지만, 팀원이 별도로 처리하는
# 소방청 일일상황보고(fire_events) 쪽 서술형 텍스트에서 뽑아낸 지역명은 약칭
# (전남, 경남 등)이라 normalized_events.sido_nm에 두 포맷이 섞이는 문제가 있었다.
# 이 테이블로 약칭을 정식명칭으로 통일한다.
SIDO_ABBR_TO_FULL = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}


def normalize_sido_name(sido: Optional[str]) -> Optional[str]:
    """
    시도 약칭(전남, 경남 등)을 정식명칭으로 변환한다.
    이미 정식명칭이거나 매핑 테이블에 없는 값이면 원문 그대로 반환한다
    (매핑 실패가 정보 손실로 이어지지 않도록 - parse_region_string과 동일한 원칙).
    None/빈 문자열이 들어오면 그대로 None/빈 문자열을 돌려준다.
    """
    if not sido:
        return sido
    return SIDO_ABBR_TO_FULL.get(sido.strip(), sido)


EMRG_STEP_TO_SEVERITY = {
    "안전안내": "NORMAL",
    "주의": "CAUTION",
    "경계": "WARNING",
    "심각": "CRITICAL",
}


_AGENCY_TAG_PATTERN = re.compile(r"\[([^\[\]]+)\]\s*$")


def extract_agency_from_msg(msg_cn: str) -> Optional[str]:
    """
    긴급재난문자 본문(MSG_CN) 끝에 붙는 '[기관명]' 표기에서 발신기관명을 추출한다.
    API 필드가 아니라 본문 텍스트 파싱 결과이므로 항상 실패할 수 있다 -> 실패 시 None.
    예: '...위험지역 출입금지. [금강홍수통제소]' -> '금강홍수통제소'
    """
    if not msg_cn:
        return None
    match = _AGENCY_TAG_PATTERN.search(msg_cn.strip())
    return match.group(1).strip() if match else None


# =======================================================================
# 2. RAW 모델 - 각 API 원본 응답 매핑
# =======================================================================

class RawCallReceipt(BaseModel):
    """전국 119 신고접수 현황. 신고자 위치와 재난 발생 위치가 분리되어 제공됨."""
    dclrRcptNo: str
    dclrDt: Optional[str] = None
    rcptEndDt: Optional[str] = None
    dsptDrtvDt: Optional[str] = None
    grndsArvlDt: Optional[str] = None
    hsptlArvlDt: Optional[str] = None
    cbkDt: Optional[str] = None
    sittnEndDt: Optional[str] = None

    ctpvNm: Optional[str] = None      # 신고자 위치
    sggNm: Optional[str] = None
    emdNm: Optional[str] = None
    dclrPstnLot: Optional[float] = None
    dclrPstnLat: Optional[float] = None

    clmtyCtpvNm: Optional[str] = None  # 재난 발생 위치 (알림 발송 기준)
    clmtySggNm: Optional[str] = None
    clmtyEmdNm: Optional[str] = None
    lot: Optional[float] = None
    lat: Optional[float] = None

    frstnNm: Optional[str] = None
    cntrNm: Optional[str] = None
    otrCtpvDclrYn: Optional[str] = None

    _zero_fields = field_validator(
        "dclrPstnLot", "dclrPstnLat", "lot", "lat"
    )(zero_to_none)


class RawFireIncident(BaseModel):
    """전국 화재 현황. 좌표 필드가 원본에 없음 -> 위치는 시군구까지만."""
    wrinvNo: str
    rcptDt: Optional[str] = None
    dsptDt: Optional[str] = None
    grndsArvlDt: Optional[str] = None
    bgnnPotfrDt: Optional[str] = None
    prfectPotfrDt: Optional[str] = None
    cbkDt: Optional[str] = None
    dsptReqHr: Optional[float] = None       # 출동소요시간. raw_fire_incidents.dspt_req_hr 매핑용 (실제 API 필드명 확인 필요 - 스키마엔 있으나 모델에 누락되어 있었음)
    fireSupesnHr: Optional[float] = None    # 진화소요시간. raw_fire_incidents.fire_supesn_hr 매핑용 (위와 동일 사유)

    ctpvNm: Optional[str] = None
    sggNm: Optional[str] = None
    frstnGrndsDstnc: Optional[float] = None  # 소방서-현장 거리. raw_fire_incidents.frstn_grnds_dstnc 매핑용
    cntrGrndsDstnc: Optional[float] = None   # 119센터-현장 거리. raw_fire_incidents.cntr_grnds_dstnc 매핑용

    frstnNm: Optional[str] = None
    cntrNm: Optional[str] = None

    fireTypeNm: Optional[str] = None
    fcltPlcLclsfNm: Optional[str] = None
    fcltPlcMclsfNm: Optional[str] = None
    fcltPlcSclsfNm: Optional[str] = None
    spfptgNm: Optional[str] = None

    dthCnt: int = 0
    injpsnCnt: int = 0
    hnlDamCnt: int = 0
    prptDamAmt: Optional[float] = None
    mubYn: Optional[str] = None             # 무허가건축물 여부(Y/N 추정). raw_fire_incidents.mub_yn 매핑용


class RawRescueIncident(BaseModel):
    """전국 구조 현황. 위치는 단일 세트(신고=현장으로 간주), 날짜가 ymd/tm으로 분리됨."""
    clmtyRscuRptpNo: str

    dclrYmd: Optional[str] = None
    dclrTm: Optional[str] = None
    dsptYmd: Optional[str] = None
    dsptTm: Optional[str] = None
    grndsArvlYmd: Optional[str] = None
    grndsArvlTm: Optional[str] = None
    rscuCmptnYmd: Optional[str] = None
    rscuCmptnTm: Optional[str] = None
    cbkYmd: Optional[str] = None
    cbkTm: Optional[str] = None

    ctpvNm: Optional[str] = None
    sggNm: Optional[str] = None
    emdNm: Optional[str] = None
    dclrPstnLot: Optional[float] = None
    dclrPstnLat: Optional[float] = None

    frstnNm: Optional[str] = None
    cntrNm: Optional[str] = None

    acdntCsNm: Optional[str] = None
    acdntPlcDtlNm: Optional[str] = None
    prcsRsltSeNm: Optional[str] = None

    _zero_fields = field_validator(
        "dclrPstnLot", "dclrPstnLat"
    )(zero_to_none)


class RawOfficialAlert(BaseModel):
    """
    행정안전부 긴급재난문자 (safetydata.go.kr DSSP-IF-00247).
    다른 세 모델과 달리 필수여부가 전부 'Y'로 명세되어 있어 결측 걱정이 적다.
    RCPTN_RGN_NM 하나에 여러 지역이 콤마로 나열되는 점이 가장 큰 특징.
    """
    SN: int
    CRT_DT: str                          # 'YYYY/MM/DD HH:MM:SS'
    MSG_CN: str                          # 재난문자 본문
    RCPTN_RGN_NM: str                    # 콤마로 구분된 여러 지역 전체주소 문자열
    EMRG_STEP_NM: Optional[str] = None   # 안전안내 / 주의 / 경계 / 심각
    DST_SE_NM: Optional[str] = None      # 재해구분 (폭염/호우/기타 등)
    REG_YMD: Optional[str] = None        # 등록일시 (raw_official_alerts.reg_ymd 매핑용)
    MDFCN_YMD: Optional[str] = None      # 수정일시 (raw_official_alerts.mdfcn_ymd 매핑용)


# =======================================================================
# 3. NORMALIZED: 알림 서비스가 실제로 사용하는 통합 이벤트 모델
# =======================================================================

class IncidentType(str, Enum):
    FIRE = "FIRE"
    RESCUE = "RESCUE"
    CALL_RECEIPT = "CALL_RECEIPT"
    OFFICIAL_ALERT = "OFFICIAL_ALERT"   # 검증된 공식 알림 (실제 CBS 발송 문자)


class LocationPrecision(str, Enum):
    COORDINATE = "COORDINATE"           # 좌표 보유
    EUPMYEONDONG = "EUPMYEONDONG"       # 읍면동까지만
    SIGUNGU = "SIGUNGU"                 # 시군구까지만 (화재의 기본 상한)


class NormalizedEvent(BaseModel):
    event_id: str                        # 전역 유일 (raw PK와 달리 fan-out으로 1:N일 수 있어 이것만 PK)
    incident_type: IncidentType
    source_pk: str                       # raw_* 테이블 조인용. 유일하지 않을 수 있음 (긴급재난문자)

    occurred_at: datetime

    sido_nm: Optional[str] = None
    sigungu_nm: Optional[str] = None
    eupmyeondong_nm: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    location_precision: LocationPrecision

    summary_title: Optional[str] = None
    severity_hint: Optional[str] = None  # NORMAL / CAUTION / WARNING / CRITICAL / CASUALTY


# =======================================================================
# 4. 변환 함수: Raw -> NormalizedEvent
# =======================================================================

def from_call_receipt(raw: RawCallReceipt) -> Optional[NormalizedEvent]:
    """재난 발생 위치(clmty*)를 기준으로 삼는다. occurred_at 파싱 실패 시 None."""
    occurred_at = parse_yyyymmddhhmmss(raw.dclrDt)
    if occurred_at is None:
        return None

    has_coord = raw.lat is not None and raw.lot is not None
    precision = LocationPrecision.COORDINATE if has_coord else LocationPrecision.EUPMYEONDONG

    return NormalizedEvent(
        event_id=f"CALL_RECEIPT:{raw.dclrRcptNo}",
        incident_type=IncidentType.CALL_RECEIPT,
        source_pk=raw.dclrRcptNo,
        occurred_at=occurred_at,
        sido_nm=normalize_sido_name(raw.clmtyCtpvNm),
        sigungu_nm=raw.clmtySggNm,
        eupmyeondong_nm=raw.clmtyEmdNm,
        lon=raw.lot,
        lat=raw.lat,
        location_precision=precision,
        summary_title=f"{raw.clmtySggNm or raw.clmtyCtpvNm} 119 신고 접수",
    )


def from_fire_incident(raw: RawFireIncident) -> Optional[NormalizedEvent]:
    """화재는 좌표가 없으므로 항상 SIGUNGU 정밀도로 취급."""
    occurred_at = parse_yyyymmddhhmmss(raw.dsptDt) or parse_yyyymmddhhmmss(raw.rcptDt)
    if occurred_at is None:
        return None

    severity = "CASUALTY" if (raw.dthCnt > 0 or raw.injpsnCnt > 0) else "NORMAL"

    return NormalizedEvent(
        event_id=f"FIRE:{raw.wrinvNo}",
        incident_type=IncidentType.FIRE,
        source_pk=raw.wrinvNo,
        occurred_at=occurred_at,
        sido_nm=normalize_sido_name(raw.ctpvNm),
        sigungu_nm=raw.sggNm,
        eupmyeondong_nm=None,
        lon=None,
        lat=None,
        location_precision=LocationPrecision.SIGUNGU,
        summary_title=f"{raw.sggNm or raw.ctpvNm} 화재 발생 ({raw.fireTypeNm or '유형미상'})",
        severity_hint=severity,
    )


def from_rescue_incident(raw: RawRescueIncident) -> Optional[NormalizedEvent]:
    """구조현황은 신고 위치를 곧 현장 위치로 간주한다."""
    occurred_at = parse_ymd_tm(raw.dsptYmd, raw.dsptTm) or parse_ymd_tm(raw.dclrYmd, raw.dclrTm)
    if occurred_at is None:
        return None

    has_coord = raw.dclrPstnLat is not None and raw.dclrPstnLot is not None
    precision = LocationPrecision.COORDINATE if has_coord else LocationPrecision.EUPMYEONDONG

    return NormalizedEvent(
        event_id=f"RESCUE:{raw.clmtyRscuRptpNo}",
        incident_type=IncidentType.RESCUE,
        source_pk=raw.clmtyRscuRptpNo,
        occurred_at=occurred_at,
        sido_nm=normalize_sido_name(raw.ctpvNm),
        sigungu_nm=raw.sggNm,
        eupmyeondong_nm=raw.emdNm,
        lon=raw.dclrPstnLot,
        lat=raw.dclrPstnLat,
        location_precision=precision,
        summary_title=f"{raw.sggNm or raw.ctpvNm} 구조 출동 ({raw.acdntCsNm or '원인미상'})",
    )


def from_official_alert(raw: RawOfficialAlert) -> list[NormalizedEvent]:
    """
    유일하게 리스트를 반환한다. RCPTN_RGN_NM에 여러 지역이 콤마로 나열되어 있으면
    지역별로 이벤트를 하나씩 만든다 (알림 서비스가 "내 지역 알림만" 조회하기 쉽도록).
    """
    occurred_at = parse_slash_datetime(raw.CRT_DT)
    if occurred_at is None:
        return []

    severity = EMRG_STEP_TO_SEVERITY.get(raw.EMRG_STEP_NM, "NORMAL")
    regions = [r for r in raw.RCPTN_RGN_NM.split(",") if r.strip()]

    events: list[NormalizedEvent] = []
    for idx, region in enumerate(regions):
        sido, sigungu, eupmyeondong = parse_region_string(region)
        sido = normalize_sido_name(sido)
        precision = LocationPrecision.EUPMYEONDONG if eupmyeondong else LocationPrecision.SIGUNGU

        events.append(NormalizedEvent(
            event_id=f"OFFICIAL_ALERT:{raw.SN}:{idx}",
            incident_type=IncidentType.OFFICIAL_ALERT,
            source_pk=str(raw.SN),
            occurred_at=occurred_at,
            sido_nm=sido,
            sigungu_nm=sigungu,
            eupmyeondong_nm=eupmyeondong,
            lon=None,
            lat=None,
            location_precision=precision,
            summary_title=f"[{raw.DST_SE_NM or '안전안내'}] {raw.MSG_CN[:40]}",
            severity_hint=severity,
        ))
    return events
