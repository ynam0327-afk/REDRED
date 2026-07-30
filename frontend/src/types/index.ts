export type Verdict = "safe" | "danger" | "neutral";

// 실제 서버가 주는 문자 판별 응답 구조 (Swagger MessageOut 기준)
export interface ApiMessage {
  message_id: number;
  received_at: string;
  raw_text: string;
  detected_urls: string[];
  url_risk_score: number;
  text_authenticity_score: number;
  matched_sido_nm: string | null;
  matched_sigungu_nm: string | null;
  matched_event_id: string | null;
  smishing_score: number;
  verdict: string; // 실제 값(안전/위험/일반 표기 방식)이 아직 명확치 않아 string으로 받고 정규화함
  device_id: string;
  created_at: string;
}

// 실제 서버가 주는 재난 이벤트 구조 (Swagger EventBrief/EventOut 기준)
export interface EventApi {
  event_id: string;
  summary_title: string | null;
  occurred_at: string;
  sido_nm: string | null;
  sigungu_nm: string | null;
  // 아래는 EventOut에만 있을 수 있는 필드 (List Events 응답이 어느 쪽인지 확인 필요)
  incident_type?: string;
  eupmyeondong_nm?: string | null;
  severity_hint?: string | null;
  is_notified?: boolean;
}

// 화면(UI)에서 쓰는 형태
export interface Message {
  id: string;
  receivedAtISO: string;
  sender: string;
  content: string;
  verdict: Verdict;
  receivedAt: string;
  reported?: boolean;
  reason?: {
    officialData: string;
    riskFactor: string;
  };
}

export interface DisasterAlertUi {
  id: string;
  typeCode: string;
  disasterType: string;
  region: string;
  message: string;
  date: string;
}