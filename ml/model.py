import re
import joblib
import numpy as np
import pandas as pd
from urllib.parse import urlparse

FEATURE_COLS = [
    "url_length", "domain_length", "dot_count", "slash_count", "hyphen_count",
    "digit_count", "contains_at", "has_ip", "https_flag", "shortener",
    "suspicious_word_count",
]

# 2주차 도메인 구조 분석 모듈(domain_analyzer.py)과 동일한 단축 URL 목록.
# 두 모듈이 서로 다른 리스트를 쓰면 shortener 피처가 어긋나므로 반드시 동기화 유지.
SHORTENER_DOMAINS = {
    "vo.la", "url.kr", "bit.ly", "han.gl", "t.ly", "goo.gl", "tinyurl.com",
    "t.co", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rb.gy",
}

SUSPICIOUS_WORDS = ["login", "verify", "secure", "account", "update", "confirm", "banking"]


def extract_url_features(raw_url: str) -> dict:
    """URL 문자열 하나에서 학습 때 쓰인 11개 피처를 동일한 방식으로 추출한다."""
    url = str(raw_url).strip()
    if not re.match(r"^https?://", url):
        url = "http://" + url

    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    return {
        "url_length": len(url),
        "domain_length": len(domain),
        "dot_count": url.count("."),
        "slash_count": url.count("/"),
        "hyphen_count": url.count("-"),
        "digit_count": sum(c.isdigit() for c in url),
        "contains_at": int("@" in url),
        "has_ip": int(bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", domain))),
        "https_flag": int(url.startswith("https")),
        "shortener": int(domain in SHORTENER_DOMAINS),
        "suspicious_word_count": sum(w in url.lower() for w in SUSPICIOUS_WORDS),
    }


def load_url_model(path: str):
    return joblib.load(path)


# 2주차 domain_analyzer.py와 동일한 화이트리스트 - 모델보다 먼저 확인한다.
OFFICIAL_DOMAINS = {
    "safekorea.go.kr", "korea119.go.kr", "nfa.go.kr", "weather.go.kr", "kma.go.kr",
    "vo.la", "url.kr",
}
OFFICIAL_TLD_SUFFIXES = (".go.kr",)


def is_official_domain(domain: str) -> bool:
    if any(domain == d or domain.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return True
    return any(domain.endswith(suffix) for suffix in OFFICIAL_TLD_SUFFIXES)


def url_risk_score_model(raw_url: str, model) -> float:
    url = str(raw_url).strip()
    if not re.match(r"^https?://", url):
        url = "http://" + url
    domain = urlparse(url).netloc.lower()

    if is_official_domain(domain):
        return 0.0

    features = extract_url_features(raw_url)
    X = pd.DataFrame([features])[FEATURE_COLS]
    proba = model.predict_proba(X)[0][1]
    return float(proba)


def disaster_reliability_score(match_info: dict) -> dict:
    if not match_info.get("region_match"):
        return {
            "score": 0.5,
            "note": "정보 부족 - 관할 시군구에 대응하는 소방청 사건 없음 (판단보류, 위험 아님)",
        }

    score = 0.5
    score += 0.2 * int(match_info.get("disaster_type_match", 0))
    score += 0.2 * match_info.get("text_similarity", 0.0)
    score += 0.1 * (1 - min(match_info.get("time_diff_hours", 24) / 24, 1))

    return {"score": round(min(score, 1.0), 3), "note": None}


def final_alert_score(disaster_info: dict, raw_url: str, model,
                       w1: float = 0.6, w2: float = 0.4) -> dict:
    d_result = disaster_reliability_score(disaster_info)
    d_score = d_result["score"]
    u_score = url_risk_score_model(raw_url, model) if raw_url else 0.0

    final = w1 * d_score + w2 * (1 - u_score)

    return {
        "disaster_reliability_score": d_score,
        "disaster_reliability_note": d_result["note"],
        "url_risk_score": u_score,
        "final_score": round(final, 3),
        "decision": "approve" if final >= 0.7 else ("review" if final >= 0.4 else "reject"),
    }