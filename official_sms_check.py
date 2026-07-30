import re
import os
import difflib
import time
import requests
import urllib3
import pandas as pd
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv("/content/drive/MyDrive/REDRED/.env")

API_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"
SERVICE_KEY = os.environ.get("SAFETYDATA_SERVICE_KEY", "")

REQUEST_TIMEOUT_SEC = 15
MAX_RETRIES = 3

# 원문이 진짜 동일한 발송분인지 판단하는 임계값. 다른 매칭(소방청DB 등)의
# 느슨한 유사도(0.2~0.6대)와 달리, 이건 "같은 문자인가"를 보는 거라 훨씬 높게 잡는다.
EXACT_MATCH_THRESHOLD = 0.9


def fetch_official_sms(crt_dt: str = None, rgn_nm: str = None,
                        num_of_rows: int = 100, page_no: int = 1) -> list:
    """
    crt_dt: 조회시작일자 YYYYMMDD (없으면 API 기본값 - 문서에 명시 안 돼 있어
            직접 호출해서 기본 동작 확인 필요)
    rgn_nm: 시도명/시군구명 (예: "서울특별시", "부산광역시 해운대구")
    """
    params = {
        "serviceKey": SERVICE_KEY,
        "returnType": "json",
        "numOfRows": num_of_rows,
        "pageNo": page_no,
    }
    if crt_dt:
        params["crtDt"] = crt_dt
    if rgn_nm:
        params["rgnNm"] = rgn_nm

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT_SEC, verify=False)
            resp.raise_for_status()
            data = resp.json()
            # 실제 응답 확인됨: 최상위 키는 'body'
            items = data.get("body", [])
            return items
        except requests.exceptions.RequestException as e:
            print(f"[요청 실패 {attempt}/{MAX_RETRIES}] {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 * attempt)


def normalize_for_compare(text: str) -> str:
    """비교 전 공백/개행 등을 정규화 - 줄바꿈 위치 차이 정도로 유사도가 떨어지지 않게."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def find_official_match(pasted_text: str, records: list) -> dict:
    """
    사용자가 붙여넣은 텍스트와 가장 유사한 공식 발송 기록을 찾는다.
    임계값(0.9) 이상이어야 "진짜 발송분과 일치"로 인정한다.
    """
    if not records:
        return {"matched": False, "score": 0.0, "record": None}

    norm_pasted = normalize_for_compare(pasted_text)
    best_score, best_record = 0.0, None

    for rec in records:
        msg = normalize_for_compare(rec.get("MSG_CN", ""))
        score = difflib.SequenceMatcher(None, norm_pasted, msg).ratio()
        if score > best_score:
            best_score, best_record = score, rec

    return {
        "matched": best_score >= EXACT_MATCH_THRESHOLD,
        "score": round(best_score, 4),
        "record": best_record,
    }


def official_sms_reliability(pasted_text: str, crt_dt: str, rgn_nm: str = None) -> dict:
    """
    사용자가 붙여넣은 문자를 공식 API 발송 이력과 대조해 신뢰도를 낸다.
    cross_validation.py의 combined_disaster_reliability보다 우선 적용할
    최상위 신호로 설계 - 여기서 매칭되면 사실상 진위가 확정된다.
    """
    try:
        records = fetch_official_sms(crt_dt=crt_dt, rgn_nm=rgn_nm, num_of_rows=100)
    except Exception as e:
        return {"score": None, "note": f"API 조회 실패 - {e} (하위 소스로 폴백 필요)"}

    result = find_official_match(pasted_text, records)

    if result["matched"]:
        return {
            "score": 1.0,
            "note": f"공식 발송 이력과 일치(유사도 {result['score']}) - 진위 확정",
            "matched_record": result["record"],
        }

    return {
        "score": None,  # 확정 불가 - 다른 소스로 폴백해야 함 (0.5로 단정하지 않음)
        "note": f"공식 발송 이력에서 일치하는 문자를 못 찾음(최고 유사도 {result['score']}) - 하위 소스로 폴백 필요",
    }


# ---------------------------------------------------------------------------
# 실행 예시
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 1) 먼저 실제 응답 구조부터 확인 (최상위 키 이름, 필드 실제 값 형태)
    sample = fetch_official_sms(num_of_rows=3)
    print("응답 샘플:", sample)
