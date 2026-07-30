import type { EventApi, DisasterAlertUi } from "../types";

const TYPE_LABEL: Record<string, string> = {
  FIRE: "화재",
  RESCUE: "구조",
  CALL_RECEIPT: "신고 접수",
  OFFICIAL_ALERT: "재난문자",
};

export function adaptAlert(raw: EventApi): DisasterAlertUi {
  const region = [raw.sido_nm, raw.sigungu_nm, raw.eupmyeondong_nm].filter(Boolean).join(" ");
  const rawType = raw.incident_type ?? "";

  return {
    id: raw.event_id,
    typeCode: rawType,
    disasterType: TYPE_LABEL[rawType] ?? (rawType || "재난 정보"),
    region: region || "지역 정보 없음",
    message: raw.summary_title ?? "",
    date: new Date(raw.occurred_at).toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}