import { AlertTriangle, BadgeCheck, HelpCircle } from "lucide-react";
import type { Verdict } from "../types";

const CONFIG: Record<Verdict, { chip: string; text: string; icon: React.ReactNode; label: string }> = {
  danger: { chip: "bg-danger-bg", text: "text-danger-text", icon: <AlertTriangle size={20} />, label: "위험 스미싱" },
  safe: { chip: "bg-safe-bg", text: "text-safe-text", icon: <BadgeCheck size={20} />, label: "공식 재난문자" },
  neutral: { chip: "bg-neutral-bg", text: "text-neutral-text", icon: <HelpCircle size={20} />, label: "일반 문자" },
};

export default function Alert({ verdict }: { verdict: Verdict }) {
  const c = CONFIG[verdict];
  return (
    <div className="bg-white rounded-2xl p-4 shadow-[0_8px_20px_rgba(15,17,21,0.06)] flex items-center gap-3">
      <div className={`w-11 h-11 rounded-xl ${c.chip} ${c.text} flex items-center justify-center shrink-0`}>
        {c.icon}
      </div>
      <div>
        <p className="text-xs text-muted mb-0.5">판별 결과</p>
        <p className={`text-lg font-semibold ${c.text}`}>{c.label}</p>
      </div>
    </div>
  );
}