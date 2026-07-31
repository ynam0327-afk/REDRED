
import re

SEOUL_SIGUNGU = {
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구",
    "성북구", "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구",
    "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구", "관악구",
    "서초구", "강남구", "송파구", "강동구",
}

BUSAN_SIGUNGU = {
    "중구", "서구", "동구", "영도구", "부산진구", "동래구", "남구", "북구",
    "해운대구", "사하구", "금정구", "강서구", "연제구", "수영구", "사상구",
    "기장군",
}

# "중구"처럼 서울/부산 둘 다에 있는 이름 - 이것만으로는 시도를 못 정한다
AMBIGUOUS_SIGUNGU = SEOUL_SIGUNGU & BUSAN_SIGUNGU

SIGUNGU_TO_SIDO = {}
for _g in SEOUL_SIGUNGU - AMBIGUOUS_SIGUNGU:
    SIGUNGU_TO_SIDO[_g] = "서울특별시"
for _g in BUSAN_SIGUNGU - AMBIGUOUS_SIGUNGU:
    SIGUNGU_TO_SIDO[_g] = "부산광역시"

AGENCY_TAG_PATTERN = re.compile(r'\[([^\[\]]+)\]\s*$')
SIGUNGU_TOKEN_PATTERN = re.compile(r'([가-힣]{1,5}(?:시|군|구))')
EMD_TOKEN_PATTERN = re.compile(r'([가-힣]{1,6}(?:동|읍|면|리))')


def extract_region_from_text(message: str) -> dict:
    """
    반환: {"sido": str|None, "sigungu": str|None, "emd": str|None,
           "region_string": "시도 시군구"|None, "note": str|None}

    sido=None인 경우 두 가지 의미가 있다:
      - sigungu도 None: 원문에서 지역명 자체를 못 찾음
      - sigungu는 있음: 서울/부산 표준 목록 밖의 지역(커버리지 없음) 또는
        "중구"처럼 시도가 모호한 이름
    """
    if not isinstance(message, str) or not message.strip():
        return {"sido": None, "sigungu": None, "emd": None, "region_string": None, "note": "빈 메시지"}

    stripped = message.strip()

    # 태그와 본문을 분리 - 태그 안 내용이 본문 검색에 섞이지 않게
    tag = None
    tag_m = AGENCY_TAG_PATTERN.search(stripped)
    body = stripped
    if tag_m:
        tag = tag_m.group(1).strip()
        body = stripped[: tag_m.start()]

    body_known = [t for t in SIGUNGU_TOKEN_PATTERN.findall(body) if t in SEOUL_SIGUNGU or t in BUSAN_SIGUNGU]
    tag_known = tag if tag and (tag in SEOUL_SIGUNGU or tag in BUSAN_SIGUNGU) else None

    sigungu = None
    note = None

    if body_known:
        sigungu = body_known[0]
        if len(body_known) > 1:
            note = f"본문에 시군구명이 여러 개 언급됨({', '.join(body_known)}) - 첫 번째({sigungu})를 사용"
    elif tag_known:
        sigungu = tag_known
        note = "본문에서 못 찾아 발신기관 태그로 대체"
    else:
        # 서울/부산 표준 목록엔 없지만, 그래도 "OO시/군/구" 모양의 지역명이
        # 본문이나 태그에 있는지 확인 (예: "원주시" - 커버리지 밖일 뿐 실제 지역명)
        body_any = SIGUNGU_TOKEN_PATTERN.findall(body)
        tag_any = tag if tag and SIGUNGU_TOKEN_PATTERN.fullmatch(tag) else None
        candidate = body_any[0] if body_any else tag_any

        if candidate:
            sigungu = candidate
            note = f"'{candidate}'는 서울/부산 119신고접수 커버리지 밖 지역"
        else:
            note = "본문/태그 어디에서도 지역명을 찾지 못함"

    if sigungu is None:
        return {"sido": None, "sigungu": None, "emd": None, "region_string": None, "note": note}

    if sigungu in AMBIGUOUS_SIGUNGU:
        sido = None
        note = (note + " / " if note else "") + f"'{sigungu}'는 서울/부산에 동시 존재 - 시도 특정 불가"
    else:
        sido = SIGUNGU_TO_SIDO.get(sigungu)  # 목록 밖 지역이면 None (커버리지 없음, 정상)

    # 읍면동 - 시군구명 뒤쪽 본문에서 탐색 (사건 상세 위치는 대체로 시군구 다음에 옴)
    emd = None
    idx = body.find(sigungu)
    if idx != -1:
        after_sigungu = body[idx + len(sigungu):]
        emd_m = EMD_TOKEN_PATTERN.search(after_sigungu)
        if emd_m:
            emd = emd_m.group(1)

    region_string = f"{sido} {sigungu}" if sido else sigungu

    return {"sido": sido, "sigungu": sigungu, "emd": emd, "region_string": region_string, "note": note}


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_messages = [
        "오늘 09:34 원주시 원동 한주아파트 101동 건물에서 화재 발생. 차량은 건물 주변 도로를 우회하고, 건물 내 시민은 건물 밖으로 대피하세요. [원주시]",
        "06:40 욱성화학 화재 관련하여 화재현장에 폭발위험은 전혀 없습니다 [금정구]",
        "오늘 09시 46분경 거제동 150-8 청마마이우스 오피스텔 1층에서 화재 발생 [연제구]",
        "금일 동구 55보급창에서 화재가 발생하여 연기, 분진이 다량 발생",  # 서울/부산 둘 다 있는 이름 아님(동구는 부산에만)
        "현재 5호선 열차 화재 발생 관련, 방화 방면 열차는 정상 개통 중 [서울교통공사]",  # 태그가 시군구 아님
        "오늘 저녁부터 기온 급강하로 도로결빙이 우려되오니 안전에 유의 바랍니다.",  # 지역명 자체가 없음
    ]

    for msg in test_messages:
        result = extract_region_from_text(msg)
        print(f"메시지: {msg[:45]}")
        print(f"  결과: {result}\n")
