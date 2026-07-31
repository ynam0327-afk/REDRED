from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# 1. 재난정보 교차검증
# ---------------------------------------------------------------------------

@dataclass
class SourceMatch:
    """개별 소스(소방청DB 또는 119신고접수)의 매칭 결과를 표준화한 형태."""
    matched: bool
    confidence: float = 0.0   # 그 소스 안에서의 신뢰도(예: text_similarity, 시각근접도 환산값)
    note: Optional[str] = None


from content_authenticity import content_authenticity_score


def combined_disaster_reliability(fire_db: Optional[SourceMatch],
                                   call119: Optional[SourceMatch],
                                   message: Optional[str] = None,
                                   official_match_score: Optional[float] = None) -> dict:
   
    if official_match_score is not None:
        return {
            "score": official_match_score,
            "matched_sources": ["official_sms_api"],
            "note": "긴급재난문자 공식 API 발송 이력과 원문 일치 - 진위 확정(최우선 신호)",
        }

    available = [s for s in (fire_db, call119) if s is not None]

    if not available:
        if message:
            content = content_authenticity_score(message)
            return {
                "score": content["score"],
                "matched_sources": [],
                "note": f"DB 조회 불가 - 콘텐츠 기반 판단으로 대체: {content['note']}",
            }
        return {
            "score": 0.5,
            "matched_sources": [],
            "note": "정보 부족 - 조회 가능한 소스가 아예 없음(판단보류, 위험 아님)",
        }

    fire_matched = fire_db is not None and fire_db.matched
    call119_matched = call119 is not None and call119.matched

    if not fire_matched and not call119_matched:
        if message:
            content = content_authenticity_score(message)
            return {
                "score": content["score"],
                "matched_sources": [],
                "note": f"DB 조회했지만 대응 사건 없음 - 콘텐츠 기반 판단으로 대체: {content['note']}",
            }
        return {
            "score": 0.5,
            "matched_sources": [],
            "note": "정보 부족 - 조회했지만 대응 사건 없음(판단보류, 위험 아님)",
        }

    if fire_matched and call119_matched:
        avg_conf = (fire_db.confidence + call119.confidence) / 2
        score = 0.85 + 0.15 * avg_conf
        note = "두 소스(fire_db, call119) 모두 매칭 - 최고 신뢰도"
        matched_sources = ["fire_db", "call119"]
    elif call119_matched:
        score = 0.75 + 0.25 * call119.confidence
        note = "단일 소스(call119)만 매칭 - 실증적으로 신뢰도 높은 주 신호"
        matched_sources = ["call119"]
    else:
        score = 0.6 + 0.2 * fire_db.confidence
        note = "단일 소스(fire_db)만 매칭 - 실전에서 드물게만 기여하는 보조 신호"
        matched_sources = ["fire_db"]

    return {
        "score": round(min(score, 1.0), 3),
        "matched_sources": matched_sources,
        "note": note,
    }


# ---------------------------------------------------------------------------
# 2. URL 교차검증 (화이트리스트 + RF 모델)
# ---------------------------------------------------------------------------

def url_cross_check(is_whitelisted: bool, rf_score: float) -> dict:
    
    if is_whitelisted:
        return {"risk": 0.0, "reason": "화이트리스트 매칭 - 공식 도메인"}

    if rf_score >= 0.7:
        return {"risk": rf_score, "reason": "RF 모델 고위험 판정"}
    if rf_score <= 0.3:
        return {"risk": rf_score, "reason": "RF 모델 저위험 판정"}

    return {"risk": rf_score, "reason": "RF 모델 애매 구간 - review 대상"}


# ---------------------------------------------------------------------------
# 3. 최종 통합 스코어
# ---------------------------------------------------------------------------

def final_alert_score_v2(fire_db: Optional[SourceMatch], call119: Optional[SourceMatch],
                          is_whitelisted: bool, rf_score: float,
                          message: Optional[str] = None,
                          official_match_score: Optional[float] = None,
                          w1: float = 0.6, w2: float = 0.4) -> dict:
    disaster = combined_disaster_reliability(fire_db, call119, message, official_match_score)
    url = url_cross_check(is_whitelisted, rf_score)

    final = w1 * disaster["score"] + w2 * (1 - url["risk"])

    return {
        "disaster_reliability_score": disaster["score"],
        "disaster_matched_sources": disaster["matched_sources"],
        "disaster_note": disaster["note"],
        "url_risk_score": url["risk"],
        "url_reason": url["reason"],
        "final_score": round(final, 3),
        "decision": "approve" if final >= 0.7 else ("review" if final >= 0.4 else "reject"),
    }


# ---------------------------------------------------------------------------
# 검증 - 확장 시나리오
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    scenarios = [
        ("두 소스 모두 매칭 + 안전 URL",
         SourceMatch(True, 0.8), SourceMatch(True, 0.9), True, 0.0),
        ("소방청DB만 매칭 + 안전 URL",
         SourceMatch(True, 0.6), None, True, 0.0),
        ("119만 매칭 + 안전 URL",
         SourceMatch(False), SourceMatch(True, 0.9), True, 0.0),
        ("서울/부산 외 지역, 소방청 매칭 없음 (119 커버리지 밖)",
         SourceMatch(False), None, False, 0.1),
        ("정보부족 + RF 애매",
         SourceMatch(False), SourceMatch(False), False, 0.5),
        ("정보부족 + 위험 URL",
         SourceMatch(False), SourceMatch(False), False, 0.9),
        ("두 소스 불일치(소방청은 매칭, 119는 매칭 안됨) + 안전 URL",
         SourceMatch(True, 0.5), SourceMatch(False), True, 0.0),
    ]

    for name, fire_db, call119, wl, rf in scenarios:
        result = final_alert_score_v2(fire_db, call119, wl, rf)
        print(f"[{name}]")
        print(f"  {result}\n")

    print("=== 콘텐츠 기반 판단 (DB 매칭 전혀 없을 때 원문으로 판단) ===")
    content_scenarios = [
        ("DB 매칭 없음 + 정상적인 공식 문구 + 안전 URL",
         "오늘 09:34 원주시 원동 한주아파트 101동 건물에서 화재 발생. 차량은 건물 주변 도로를 우회하고, 건물 내 시민은 건물 밖으로 대피하세요. [원주시]",
         True, 0.0),
        ("DB 매칭 없음 + 스미싱 의심 문구",
         "재난지원금 무료 쿠폰 당첨! 즉시 확인 후 인증번호 입력 http://bit.ly/abc123",
         False, 0.6),
        ("DB 매칭 없음 + 발신기관 태그 자체가 없음",
         "화재가 발생했습니다 주의하세요",
         True, 0.0),
    ]
    for name, message, wl, rf in content_scenarios:
        result = final_alert_score_v2(SourceMatch(False), SourceMatch(False), wl, rf, message=message)
        print(f"[{name}]")
        print(f"  {result}\n")

    print("=== 공식 재난문자 API 일치 (최우선 신호) ===")
    official_scenarios = [
        ("공식 API와 원문 일치 + 안전 URL",
         1.0, True, 0.0),
        ("공식 API 미일치 -> 기존 로직 폴백 + 안전 URL",
         None, True, 0.0),
    ]
    for name, official_score, wl, rf in official_scenarios:
        result = final_alert_score_v2(SourceMatch(False), SourceMatch(False), wl, rf,
                                       official_match_score=official_score)
        print(f"[{name}]")
        print(f"  {result}\n")
