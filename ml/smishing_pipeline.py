import os
import re
import ipaddress
import unicodedata

import pandas as pd

from datetime import date as date_cls
from urllib.parse import urlparse

from content_authenticity import content_authenticity_score
from text_match import match_sms_to_call119
from model import url_risk_score_model, is_official_domain, load_url_model
from official_sms_check import official_sms_reliability
from cross_validation import SourceMatch, combined_disaster_reliability
from region_extractor import extract_region_from_text


# ============================================================
# URL 전처리
# ============================================================

def normalize_text_for_url(text: str) -> str:
    """
    스미싱 우회 패턴 정규화
    """

    if not text:
        return text

    text = unicodedata.normalize("NFKC", text)

    replacements = {
        "hxxps://": "https://",
        "hxxp://": "http://",
        "[.]": ".",
        "(.)": ".",
        "{.}": ".",
        "[:]": ":",
    }

    for src, dst in replacements.items():
        text = text.replace(src, dst)

    return text


# ============================================================
# URL 추출
# - 일반 도메인
# - 단축 URL
# - IPv4 URL
# ============================================================

URL_PATTERN = re.compile(
    r"""
    (?:
        https?://
    )?
    (?:
        (?:\d{1,3}\.){3}\d{1,3}
        |
        (?:[a-zA-Z0-9]
            (?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?
            \.
        )+
        [a-zA-Z]{2,}
    )
    (?:
        /[^\s\[\]()〈〉『』]*
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def extract_first_url(raw_text: str) -> str | None:

    if not isinstance(raw_text, str):
        return None

    normalized = normalize_text_for_url(raw_text)

    matches = URL_PATTERN.findall(normalized)

    for raw in matches:

        raw = raw.rstrip(".,);]>")

        if (
            re.search(r"[a-zA-Z]{2,}", raw)
            or re.search(r"\d+\.\d+\.\d+\.\d+", raw)
        ):
            return raw

    return None


# ============================================================
# 도메인 추출
# ============================================================

def _extract_domain(url: str) -> str:

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    try:
        domain = urlparse(url).netloc.lower()

        try:
            domain = domain.encode("idna").decode("ascii")
        except Exception:
            pass

        return domain

    except Exception:
        return ""


# ============================================================
# IP URL 판별
# ============================================================

def is_ip_domain(domain: str) -> bool:

    try:
        ipaddress.ip_address(domain)
        return True

    except ValueError:
        return False


# ============================================================
# 스미싱 의심 키워드
# ============================================================

SUSPICIOUS_TERMS = [
    "지원금",
    "보상금",
    "상품권",
    "당첨",
    "계좌번호",
    "카드번호",
    "인증번호",
    "대출",
    "환급금",
]


# ============================================================
# 모델 로딩
# ============================================================

DATA_DIR = os.environ.get(
    "ML_DATA_DIR",
    "/content/drive/MyDrive/REDRED"
)

_RF_MODEL = load_url_model(
    f"{DATA_DIR}/rf_url_model.joblib"
)

_FIRE_DB = pd.read_csv(
    f"{DATA_DIR}/fire_events_region_normalized.csv"
)

_FIRE_DB["report_date"] = (
    _FIRE_DB["report_date"].astype(str)
)

_CALL119_BY_CITY = {
    "서울특별시": pd.read_parquet(
        f"{DATA_DIR}/seoul_119_2024_dates.parquet"
    ),
    "부산광역시": pd.read_csv(
        f"{DATA_DIR}/busan_119_2024_dates.csv"
    ),
}

for _df in _CALL119_BY_CITY.values():
    _df["dclr_ymd"] = _df["dclr_ymd"].astype(str)


# ============================================================
# 재난 데이터 매칭
# ============================================================

def _check_fire_db(
    region: str,
    report_date: str
) -> SourceMatch:

    if not region:
        return SourceMatch(False)

    sido = region.split()[0] if region.split() else None

    cand = _FIRE_DB[
        (_FIRE_DB["report_date"] == report_date)
        &
        (_FIRE_DB["sido_official"] == sido)
    ]

    if len(cand) == 0:
        return SourceMatch(False)

    return SourceMatch(
        True,
        confidence=0.6
    )


def _check_call119(
    message: str,
    region: str,
    sms_date: str
) -> SourceMatch:

    sido = (
        region.split()[0]
        if region and region.split()
        else None
    )

    call119_df = _CALL119_BY_CITY.get(sido)

    if call119_df is None:
        return None

    row = pd.Series({
        "date": sms_date,
        "region": region,
        "message": message,
        "disaster_type": None
    })

    result = match_sms_to_call119(
        row,
        call119_df
    )

    if result is None:
        return SourceMatch(False)

    hour_diff = result.get("hour_diff")

    confidence = (
        max(0.0, 1 - hour_diff / 12)
        if hour_diff is not None
        else 0.5
    )

    return SourceMatch(
        True,
        confidence=confidence
    )


# ============================================================
# 메인 파이프라인
# ============================================================

def process_message(
    raw_text: str,
    url: str | None = None,
    region: str | None = None,
    sms_date: str | None = None,
    official_service_key: str | None = None,
) -> dict:

    normalized_text = normalize_text_for_url(
        raw_text
    )

    if url is None:
        url = extract_first_url(
            normalized_text
        )

    region_note = None

    if region is None:
        region_result = extract_region_from_text(
            normalized_text
        )

        region = region_result["region_string"]
        region_note = region_result["note"]

    sms_date = (
        sms_date
        or date_cls.today().isoformat()
    )

    ymd = sms_date.replace("-", "")

    # ====================================================
    # URL 위험도 계산
    # ====================================================

    domain = _extract_domain(url)

    is_wl = (
        bool(url)
        and is_official_domain(domain)
    )

    if not url:

        url_risk_score = 0.0

    elif is_wl:

        url_risk_score = 0.0

    elif is_ip_domain(domain):

        # IP URL 즉시 최고 위험도
        url_risk_score = 1.0

    else:

        url_risk_score = url_risk_score_model(
            url,
            _RF_MODEL
        )

    # 지원금/당첨 등 위험 키워드 보정
    if any(
        term in normalized_text
        for term in SUSPICIOUS_TERMS
    ):
        url_risk_score = min(
            1.0,
            url_risk_score + 0.3
        )

    # ====================================================
    # 공식 재난문자 검증
    # ====================================================

    official_score = None

    if official_service_key:

        try:

            official_result = (
                official_sms_reliability(
                    normalized_text,
                    ymd,
                    region
                )
            )

            official_score = official_result.get(
                "score"
            )

        except Exception:

            official_score = None

    fire_db_match = _check_fire_db(
        region,
        sms_date
    )

    call119_match = _check_call119(
        normalized_text,
        region,
        sms_date
    )

    disaster = combined_disaster_reliability(
        fire_db_match,
        call119_match,
        normalized_text,
        official_score
    )

    # 재난 관련 문구/형식이 전혀 없는 일반 문자면 disaster["score"]가 None으로 옴.
    # DB 저장용으로는 중립값(0.5)을 채워 넣되, 실제 판정(verdict)은
    # is_disaster_message 플래그를 보고 notification-service에서 별도 처리한다.
    is_disaster_message = disaster.get("is_disaster_format", True)
    text_authenticity_score = (
        disaster["score"] if disaster["score"] is not None else 0.5
    )

    return {
        "url_risk_score": round(
            float(url_risk_score),
            4
        ),
        "text_authenticity_score":
            text_authenticity_score,
        "is_disaster_message":
            is_disaster_message,
        "detail": {
            "url_used": url,
            "domain": domain,
            "url_whitelisted": is_wl,
            "region_used": region,
            "region_extraction_note":
                region_note,
            "disaster_matched_sources":
                disaster["matched_sources"],
            "disaster_note":
                disaster["note"],
        },
    }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":

    tests = [
        "http://98.91.24.83",
        "hxxps://safe-help.kr",
        "https://gοv-support.kr",
        "vo.la/Vo27SU",
        "https://www.mois.go.kr"
    ]

    for t in tests:
        print("=" * 60)
        print(t)
        print(extract_first_url(t))