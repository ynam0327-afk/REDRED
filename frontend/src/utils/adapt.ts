import type { ApiMessage, Message, Verdict } from "../types";

function normalizeVerdict(raw: string): Verdict {
  const v = (raw ?? "").toLowerCase();
  if (v.includes("danger") || v.includes("smishing") || v.includes("위험")) return "danger";
  if (v.includes("safe") || v.includes("authentic") || v.includes("안전")) return "safe";
  return "neutral";
}

export function adaptMessage(raw: ApiMessage): Message {
  const hasMatch = Boolean(raw.matched_event_id);
  const region = [raw.matched_sido_nm, raw.matched_sigungu_nm].filter(Boolean).join(" ");

  return {
    id: String(raw.message_id),
    receivedAtISO: raw.received_at,
    sender: "발신 정보 없음",
    content: raw.raw_text,
    verdict: normalizeVerdict(raw.verdict),
    receivedAt: new Date(raw.received_at).toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
    reason: hasMatch
      ? {
          officialData: `${region || "해당 지역"}의 공식 재난 이벤트(ID: ${raw.matched_event_id})와 매칭되었습니다.`,
          riskFactor: `URL 위험도 ${Math.round(raw.url_risk_score * 100)}%, 텍스트 신뢰도 ${Math.round(
            raw.text_authenticity_score * 100
          )}%`,
        }
      : undefined,
  };
}