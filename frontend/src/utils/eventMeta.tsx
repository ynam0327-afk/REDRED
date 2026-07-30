import { Flame, LifeBuoy, PhoneIncoming, Siren, HelpCircle } from "lucide-react";

export const EVENT_LABEL: Record<string, string> = {
  FIRE: "화재",
  RESCUE: "구조",
  CALL_RECEIPT: "신고 접수",
  OFFICIAL_ALERT: "재난문자",
};

export const EVENT_META: Record<string, { icon: React.ReactNode; bg: string; text: string; accent: string }> = {
  FIRE: { icon: <Flame size={18} />, bg: "bg-danger-bg", text: "text-danger-text", accent: "bg-danger" },
  RESCUE: { icon: <LifeBuoy size={18} />, bg: "bg-safe-bg", text: "text-safe-text", accent: "bg-safe" },
  CALL_RECEIPT: { icon: <PhoneIncoming size={18} />, bg: "bg-gray-100", text: "text-gray-500", accent: "bg-gray-300" },
  OFFICIAL_ALERT: { icon: <Siren size={18} />, bg: "bg-disaster-bg", text: "text-disaster-text", accent: "bg-disaster" },
  DEFAULT: { icon: <HelpCircle size={18} />, bg: "bg-gray-100", text: "text-gray-500", accent: "bg-gray-300" },
};