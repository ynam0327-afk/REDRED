import re
import pandas as pd

TIME_PATTERN = re.compile(r'(\d{1,2})\s*[:시]\s*(\d{1,2})?')


def extract_report_hour(message: str):
    """SMS 원문에서 '오늘 12:45' '14:12분경' '09시 46분경' 같은 시각 표현의 시(hour)를 뽑는다."""
    if not isinstance(message, str):
        return None
    m = TIME_PATTERN.search(message)
    if not m:
        return None
    hour = int(m.group(1))
    return hour if 0 <= hour <= 23 else None


def match_sms_to_call119(sms_row: pd.Series, call119_df: pd.DataFrame) -> dict:
    ymd = str(sms_row["date"]).replace("-", "")
    first_region = str(sms_row["region"]).split(",")[0]
    tokens = first_region.split()

    sido = tokens[0] if len(tokens) > 0 else None
    sigungu = tokens[1] if len(tokens) > 1 else None
    emd = tokens[2] if len(tokens) > 2 else None

    if not sigungu or sigungu == "전체":
        return None

    # dclr_ymd는 smishing_pipeline.py의 로딩 시점에 이미 문자열로 캐스팅해뒀으므로
    # (_df["dclr_ymd"] = _df["dclr_ymd"].astype(str)) 여기서 매 요청마다 다시
    # .astype(str)을 반복할 필요가 없다. 수십만 행짜리 컬럼을 요청마다 재캐스팅하는 건
    # 순수 낭비라 제거함 - 응답 속도에 실질적인 영향이 있던 부분.
    base = call119_df[
        (call119_df["dclr_ymd"] == ymd)
        & (call119_df["sido"] == sido)
        & (call119_df["sigungu"] == sigungu)
    ]

    if len(base) == 0:
        return None

    match_level = "sigungu"
    candidates = base

    if emd:
        emd_cand = base[base["emd"] == emd]
        if len(emd_cand) > 0:
            candidates = emd_cand
            match_level = "emd"

    disaster_type = sms_row.get("disaster_type")
    if isinstance(disaster_type, str):
        type_cand = candidates[candidates["incident_type"].str.contains(disaster_type, na=False)]
        if len(type_cand) > 0:
            candidates = type_cand

    sms_hour = extract_report_hour(sms_row.get("message"))
    best_report_id = None
    hour_diff = None

    if sms_hour is not None and "dclr_hr" in candidates.columns:
        diffs = (candidates["dclr_hr"] - sms_hour).abs()
        diffs = diffs.apply(lambda d: min(d, 24 - d))
        best_idx = diffs.idxmin()
        best_report_id = candidates.loc[best_idx, "report_id"]
        hour_diff = float(diffs.loc[best_idx])
    else:
        best_report_id = candidates.iloc[0]["report_id"]

    return {
        "match_level": match_level,
        "candidate_count": len(candidates),
        "best_report_id": best_report_id,
        "hour_diff": hour_diff,
    }