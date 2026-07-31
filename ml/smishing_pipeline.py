import re
import pandas as pd
from datetime import date as date_cls
from urllib.parse import urlparse

from content_authenticity import content_authenticity_score
from text_match import match_sms_to_call119
from model import url_risk_score_model, is_official_domain, load_url_model
from official_sms_check import official_sms_reliability
from cross_validation import SourceMatch, combined_disaster_reliability
from region_extractor import extract_region_from_text

# 본문에서 URL을 직접 찾는 패턴 (2주차 regex_extractor.py와 동일한 방식) -
# 스킴(http://) 유무와 무관하게 탐지해야 vo.la/xxxx 같은 단축 URL도 잡힌다.
URL_PATTERN = re.compile(
    r'(?:https?://)?'
    r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+'
    r'[a-zA-Z]{2,}'
    r'(?:/[^\s\[\]()〈〉『』]*)?'
)


def extract_first_url(raw_text: str) -> str | None:
   
    if not isinstance(raw_text, str):
        return None
    for raw in URL_PATTERN.findall(raw_text):
        raw = raw.rstrip(".,)")
        if re.search(r"[a-zA-Z]{2,}", raw):  # 순수 숫자(시각, 소수 등) 오탐 방지
            return raw
    return None


# ---------------------------------------------------------------------------
# 모듈 로드 시 딱 한 번만 실행 - 무거운 것들을 여기서 메모리에 올려둔다
# ---------------------------------------------------------------------------

import os
DATA_DIR = os.environ.get("ML_DATA_DIR", "/content/drive/MyDrive/REDRED")

_RF_MODEL = load_url_model(f"{DATA_DIR}/rf_url_model.joblib")

_FIRE_DB = pd.read_csv(f"{DATA_DIR}/fire_events_region_normalized.csv")
_FIRE_DB["report_date"] = _FIRE_DB["report_date"].astype(str)

_CALL119_BY_CITY = {
    "서울특별시": pd.read_parquet(f"{DATA_DIR}/seoul_119_2024_dates.parquet"),
    "부산광역시": pd.read_csv(f"{DATA_DIR}/busan_119_2024_dates.csv"),
}
for _df in _CALL119_BY_CITY.values():
    _df["dclr_ymd"] = _df["dclr_ymd"].astype(str)


# ---------------------------------------------------------------------------
# 개별 소스 조회 함수
# ---------------------------------------------------------------------------

def _check_fire_db(region: str, report_date: str) -> SourceMatch:
    if not region:
        return SourceMatch(False)
    sido = region.split()[0] if region.split() else None
    cand = _FIRE_DB[(_FIRE_DB["report_date"] == report_date) & (_FIRE_DB["sido_official"] == sido)]
    if len(cand) == 0:
        return SourceMatch(False)
    return SourceMatch(True, confidence=0.6)


def _check_call119(message: str, region: str, sms_date: str) -> SourceMatch:
    sido = region.split()[0] if region and region.split() else None
    call119_df = _CALL119_BY_CITY.get(sido)
    if call119_df is None:
        return None  # 서울/부산 외 지역 - 애초에 커버리지 없음(정보부족 처리 대상)

    row = pd.Series({"date": sms_date, "region": region, "message": message,
                      "disaster_type": None})
    result = match_sms_to_call119(row, call119_df)
    if result is None:
        return SourceMatch(False)

    hour_diff = result.get("hour_diff")
    confidence = max(0.0, 1 - hour_diff / 12) if hour_diff is not None else 0.5
    return SourceMatch(True, confidence=confidence)


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return urlparse(url).netloc.lower()


# ---------------------------------------------------------------------------
# 외부(ingest-worker 등)에서 부르는 단일 진입점
# ---------------------------------------------------------------------------

def process_message(raw_text: str, url: str | None = None, region: str | None = None,
                     sms_date: str | None = None,
                     official_service_key: str | None = None) -> dict:
   
    if url is None:
        url = extract_first_url(raw_text)

    region_note = None
    if region is None:
        region_result = extract_region_from_text(raw_text)
        region = region_result["region_string"]
        region_note = region_result["note"]

    sms_date = sms_date or date_cls.today().isoformat()
    ymd = sms_date.replace("-", "")

    # 1) URL 위험도 - model.py의 RF 모델 사용 (domain_module의 규칙 기반은 안 씀)
    domain = _extract_domain(url)
    is_wl = bool(url) and is_official_domain(domain)
    url_risk_score = 0.0 if (not url or is_wl) else url_risk_score_model(url, _RF_MODEL)

    # 2) 재난정보 신뢰도 - 공식API > (소방청DB + 119신고접수 결합) > 콘텐츠 판단 순
    official_score = None
    if official_service_key:
        try:
            official_result = official_sms_reliability(raw_text, ymd, region)
            official_score = official_result.get("score")
        except Exception:
            official_score = None  # API 장애 시에도 파이프라인은 계속 진행

    fire_db_match = _check_fire_db(region, sms_date)
    call119_match = _check_call119(raw_text, region, sms_date)

    disaster = combined_disaster_reliability(
        fire_db_match, call119_match, raw_text, official_score
    )

    return {
        "url_risk_score": round(url_risk_score, 4),
        "text_authenticity_score": disaster["score"],
        "detail": {
            "url_used": url,
            "url_whitelisted": is_wl,
            "region_used": region,
            "region_extraction_note": region_note,
            "disaster_matched_sources": disaster["matched_sources"],
            "disaster_note": disaster["note"],
        },
    }


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # url, region 둘 다 안 넘김 - 본문에서 URL과 지역 모두 자동 추출되는지 확인
    result = process_message(
        raw_text="오늘 05:50 미평천 청주시(장성2교)지점 심각단계. 하천범람에 대비 바랍니다. 내 위치, 침수우려지역 확인 vo.la/Vo27SU [금강홍수통제소]",
        sms_date="2025-05-15",
    )
    print(result)
