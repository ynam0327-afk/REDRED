import re

# 공식 재난문자에서 실제로 반복 확인되는 문구 (2주차~4주차 실데이터에서 관찰)
OFFICIAL_PHRASE_MARKERS = [
    "안전에 유의", "대피", "출입금지", "우회", "통제", "자제",
    "확인바랍니다", "주의바랍니다", "발생", "예상", "발효",
]

# 스미싱 특유의 긴급성+보상미끼+클릭유도 조합 (실제 스미싱 샘플로 검증 필요 - 추정치)
SMISHING_RED_FLAGS = [
    "당첨", "무료", "쿠폰", "즉시 확인", "링크를 클릭", "인증번호",
    "환급", "대출", "저금리", "선착순", "본인확인", "계좌",
]

AGENCY_SUFFIXES = (
    "시청", "군청", "구청", "청", "통제소", "부", "본부", "센터",
    "시", "군", "구", "도", "경찰서", "소방서", "공사", "처",
)

AGENCY_TAG_PATTERN = re.compile(r'\[([^\[\]]+)\]\s*$')

# 재난문자를 흉내내려는 최소한의 시도가 있는지 판단하는 키워드
# (재난 유형/경보 관련 어휘 - 실데이터에서 관찰된 것들)
DISASTER_TOPIC_KEYWORDS = [
    "호우", "폭염", "한파", "대설", "태풍", "지진", "화재", "산불", "홍수",
    "침수", "강풍", "미세먼지", "재난", "경보", "주의보", "위험지역", "안전안내문자",
]


def extract_agency_tag(message: str):
    """문장 끝 대괄호에서 발신 기관명을 뽑는다. 없으면 None."""
    if not isinstance(message, str):
        return None
    m = AGENCY_TAG_PATTERN.search(message.strip())
    return m.group(1).strip() if m else None


def content_authenticity_signals(message: str) -> dict:
    """
    문자 원문만으로 판단 가능한 신호들을 계산한다.
    DB 매칭 여부와 완전히 무관 - 텍스트 자체의 형식/어휘만 본다.
    """
    if not isinstance(message, str):
        message = ""

    agency = extract_agency_tag(message)
    agency_valid = bool(agency) and agency.endswith(AGENCY_SUFFIXES)

    official_marker_count = sum(p in message for p in OFFICIAL_PHRASE_MARKERS)
    red_flag_count = sum(p in message for p in SMISHING_RED_FLAGS)

    return {
        "agency_tag": agency,
        "agency_tag_present": agency is not None,
        "agency_pattern_valid": agency_valid,
        "official_marker_count": official_marker_count,
        "smishing_red_flag_count": red_flag_count,
    }


def is_disaster_related(message: str) -> bool:
    """
    재난문자 형식/어휘를 흉내내려는 최소한의 시도라도 있는지 판단한다.
    발신기관 태그, 공식 문구, 재난 유형 키워드 중 하나도 없으면
    재난문자와 아예 무관한 일반 문자로 본다.
    (스미싱 의심 표현 여부는 여기서 따지지 않는다 - 그건 호출부에서 별도로 먼저 체크함)
    """
    if not isinstance(message, str):
        return False
    sig = content_authenticity_signals(message)
    if sig["agency_tag_present"] or sig["official_marker_count"] > 0:
        return True
    return any(kw in message for kw in DISASTER_TOPIC_KEYWORDS)


def content_authenticity_score(message: str) -> dict:
    """
    문자 원문만으로 낸 신뢰도 점수(0~1)와 근거.
    DB 매칭이 전혀 없을 때 disaster_reliability=0.5(중립) 대신
    이 점수로 대체하거나 블렌딩하는 용도.

    반환값의 is_disaster_format이 False면 score는 의미가 없으므로(None) 호출부는
    점수를 쓰는 대신 "재난문자 자체가 아님"으로 처리해야 한다.
    (재난과 무관한 임의의 문자가 우연히 포함한 단어 때문에 위험/공식으로
    오락가락 분류되던 문제를 여기서 먼저 걸러낸다)
    """
    sig = content_authenticity_signals(message)

    # 스미싱 신호가 하나라도 있으면 강하게 감점 (공식 문자에서 발견될 이유가 없는 문구들)
    # 재난 형식 여부와 무관하게 위험 신호이므로 계속 판별 대상으로 취급한다.
    if sig["smishing_red_flag_count"] > 0:
        score = max(0.0, 0.3 - 0.1 * sig["smishing_red_flag_count"])
        note = f"스미싱 의심 표현 {sig['smishing_red_flag_count']}개 발견 - 위험 신호"
        return {"score": round(score, 3), "signals": sig, "note": note, "is_disaster_format": True}

    if not is_disaster_related(message):
        return {
            "score": None,
            "signals": sig,
            "note": "재난 관련 문구/형식이 전혀 없음 - 재난문자 자체가 아닌 것으로 판단",
            "is_disaster_format": False,
        }

    score = 0.5  # 기본값 - 정보부족과 동일한 출발점
    if sig["agency_tag_present"]:
        score += 0.15 if sig["agency_pattern_valid"] else -0.1
    score += min(sig["official_marker_count"] * 0.05, 0.15)

    score = max(0.0, min(1.0, score))

    note_parts = []
    if sig["agency_tag_present"]:
        note_parts.append(f"발신기관 태그 {'유효' if sig['agency_pattern_valid'] else '형식 이상'}({sig['agency_tag']})")
    else:
        note_parts.append("발신기관 태그 없음")
    note_parts.append(f"공식 문구 {sig['official_marker_count']}개 포함")

    return {"score": round(score, 3), "signals": sig, "note": " / ".join(note_parts), "is_disaster_format": True}