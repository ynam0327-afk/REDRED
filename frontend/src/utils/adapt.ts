import type { ApiMessage, Message, Verdict } from "../types";

function normalizeVerdict(raw: string): Verdict {
  const v = (raw ?? "").toLowerCase();
  if (v.includes("not_disaster")) return "not_disaster";
  if (v.includes("danger") || v.includes("smishing") || v.includes("위험")) return "danger";
  if (v.includes("safe") || v.includes("authentic") || v.includes("안전")) return "safe";
  return "neutral";
}

export function adaptMessage(raw: ApiMessage): Message {
  const hasMatch = Boolean(raw.matched_event_id);
  const region = [raw.matched_sido_nm, raw.matched_sigungu_nm].filter(Boolean).join(" ");

  // verification이 오면 그걸 우선 쓰고, 없으면(과도기) 예전 필드로 폴백
  const rawStatus = raw.verification?.status ?? raw.verdict ?? "";
  const score = raw.verification?.score ?? raw.smishing_score;

  return {
    id: String(raw.message_id),
    receivedAtISO: raw.received_at,
    sender: "발신 정보 없음",
    content: raw.raw_text,
    verdict: normalizeVerdict(rawStatus),
    receivedAt: new Date(raw.received_at).toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
    }),
    reason: hasMatch
      ? {
          officialData: `${region || "해당 지역"}의 공식 재난 이벤트(ID: ${raw.matched_event_id})와 매칭되었습니다.`,
          riskFactor:
            score != null
              ? `종합 위험도 ${Math.round(score * 100)}%`
              : raw.url_risk_score != null && raw.text_authenticity_score != null
              ? `URL 위험도 ${Math.round(raw.url_risk_score * 100)}%, 텍스트 신뢰도 ${Math.round(
                  raw.text_authenticity_score * 100
                )}%`
              : "판별 점수 없음",
        }
      : undefined,
  };
}