# REDRED
소방안전 빅데이터 플랫폼의 실시간 재난/출동 데이터를 기반으로 해당 지역 사용자에게 검증된 공식 푸시 알림을 제공하는 앱입니다.

## 🗂️ 폴더 구조
<img src="https://hits.seeyoufarm.com/api/count/incr/badge.svg?url=https%3A%2F%2Fgithub.com%2Fblurfx&count_bg=%2379C83D&title_bg=%23555555&icon=&icon_color=%23E7E7E7&title=hits&edge_flat=false" width="0" height="0" />

```json

{
  REDRED-main/
├── backend/
│   ├── collector-service/    # 공식 데이터 4종을 주기적으로 폴링해서 Redis Stream에 넣음
│   ├── ingest-worker/        # Redis Stream을 구독해서 DB(normalized_events)에 정규화 적재
│   ├── notification-service/ # FastAPI 서버. 프론트가 직접 호출하는 유일한 서비스 (API 게이트웨이 역할)
│   ├── shared/                # 3개 서비스가 공유하는 DB 스키마/모델 정의
│   └── docker-compose.yml    # postgres, redis, 3개 서비스를 한 번에 띄우는 설정
├── ml/                        # 스미싱 판별 로직 (URL 위험도 + 재난정보 신뢰도)
├── frontend/                  # React(Vite) + TypeScript + Tailwind 앱
└── domain/, data.ipynb        # 초기 데이터 탐색용 노트북 (운영 파이프라인과는 무관)
}
```
---
